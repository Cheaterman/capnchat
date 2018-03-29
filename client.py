#!/usr/bin/env python

from __future__ import print_function
import capnp
import sys
import threading
import time
import queue
from chatroom_capnp import Client as Capnp_Client, ChatServer, Login, Message


SERVER_ADDRESS = 'tms-server.com:50000'


class Commands(object):
    def __init__(self, user, **kwargs):
        self.user = user

    def prompt(self, channel):
        return '{}> '.format(('#' + channel) if channel else '')

    @property
    def list(self):
        return {
            attribute.replace('on_', ''): getattr(self, attribute)
            for attribute in dir(self)
            if attribute.startswith('on_')
            and callable(getattr(self, attribute))
        }

    def evaluate(self, message):
        if message and not message.startswith('/'):
            self.user.send(message)
            return
        words = message[1:].split()
        if not words:
            return
        message, arguments = words[0], words[1:]
        for command, callback in self.list.items():
            if command != message:
                continue
            try:
                callback(*arguments)
            except TypeError as e:
                print(e)
                raise ValueError(
                    'Invalid argument count for command "%s"!' % message
                )
            break
        else:
            raise ValueError('Unknown command "%s"!' % message)

    def on_nick(self, nickname):
        self.user.nick(nickname)

    def on_join(self, room):
        self.user.join(room)

    def on_list(self):
        self.user.list()

    def on_quit(self):
        global quit
        quit = True


class Client(Capnp_Client.Server):
    def __init__(self, user):
        self.user = user

    def receive(self, message, _context):
        user = self.user
        print('\r', end='')
        user.print_message(message)
        print(user.commands.prompt(
            user.current_room.name
            if user.current_room else None
        ), end='')
        sys.stdout.flush()


class Room(object):
    def __init__(self, name, room):
        self.name = name
        self._room = room

    def __getattr__(self, name):
        try:
            attr = getattr(self._room, name)
        except AttributeError:
            return super(Room, self).__getattr__(name)
        return attr


class User(object):
    def __init__(self, login, nickname='', **kwargs):
        self.login = login
        self.nickname = nickname
        self.commands = Commands(user=self)

        self.client = None
        self.server = None
        self.handle = None
        self.current_room = None
        self.joined_rooms = {}

    def nick(self, name):
        self.nickname = name
        if not self.client:
            self.client = client = Client(self)
            result = self.login.login(client, name).wait()
            self.server, self.handle = result.server, result.handle
        else:
            self.server.nick(name).wait()

    def join(self, room):
        if not self.client:
            print("Can't join a room without a nickname!")
            return
        print('Joining room "{}"'.format(room))
        chat_room = self.get_room(room)
        messages = chat_room.get().wait().messages
        for message in messages:
            self.print_message(message)
        if not messages:
            print('Empty channel!')
        self.current_room = chat_room

    def list(self):
        if not self.client:
            print("Can't list rooms without a nickname!")
            return
        for room in self.server.list().wait().rooms:
            print(room)

    def send(self, message):
        if not self.current_room:
            print("Can't send a message without joining a room!")
            return
        self.current_room.send(message).wait()

    def print_message(self, message):
        print('{}: {}'.format(message.author, message.content))

    def get_room(self, name):
        if name in self.joined_rooms:
            return self.joined_rooms[name]
        self.joined_rooms[name] = room = Room(
            name=name,
            room=self.server.join(name).wait().room,
        )
        return room


if __name__ == '__main__':
    try:
        input = raw_input
    except NameError:
        pass

    client = capnp.TwoPartyClient(SERVER_ADDRESS)
    login = client.bootstrap().cast_as(Login)
    user = User(login=login)
    command_queue = queue.Queue()
    command_lock = threading.Lock()

    def get_input():
        while True:
            try:
                with command_lock:
                    command_queue.put(
                        input(user.commands.prompt(
                            user.current_room.name
                            if user.current_room else None
                        ))
                    )
            except EOFError:
                break
            time.sleep(.01)

    command_thread = threading.Thread(target=get_input)
    command_thread.daemon = True
    quit = False

    print('ChatRoom v0.1')
    print('Commands: {}'.format(', '.join([
        '"%s"' % command for command in user.commands.list
    ])))
    command_thread.start()

    while not quit:
        try:
            command = command_queue.get(False)
        except queue.Empty:
            command = None

        if command:
            with command_lock:
                try:
                    user.commands.evaluate(command)
                except ValueError as exception:
                    print('ERROR: %s' % exception.message)

        capnp.getTimer().after_delay(.01 * 10 ** 9).wait()

        if not command_thread.is_alive():
            quit = True
