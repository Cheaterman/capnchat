from __future__ import print_function
import capnp
import sys
import threading
import time
import queue
from chatroom_capnp import Chat, Message


SERVER_ADDRESS = 'tms-server.com:50000'


class Commands(object):
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
            user.send(message)
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
        user.nickname = nickname

    def on_join(self, room):
        user.join(room)

    def on_list(self):
        for room in chat.getAllRooms().wait().rooms:
            print('{}: {}'.format(room.id, room.name))

    def on_quit(self):
        global quit
        quit = True


class User(object):
    def __init__(self, nickname='', joined_rooms=[], **kwargs):
        self.nickname = nickname
        self.joined_rooms = {
            room: chat.getRoom(room).wait().room for room in joined_rooms
        }
        self.current_room = None
        self.last_message = None

    def join(self, room):
        if not self.nickname:
            print("Can't join a room without a nickname!")
            return
        print('Joining room "{}"'.format(room))
        room = self.get_room(room)
        for message in room.messages:
            self.print_message(message)
        if not room.messages:
            print('Empty channel!')
        else:
            self.last_message = message
        self.current_room = room

    def send(self, message):
        if not self.current_room:
            print("Can't send a message without joining a room!")
            return
        message = Message.new_message(
            author=self.nickname,
            content=message,
        )
        self.last_message = message = chat.sendMessage(
            self.current_room.name,
            message
        ).wait().new_message

    def print_message(self, message):
        print('{}: {}'.format(message.author, message.content))

    def get_room(self, name):
        self.joined_rooms[name] = room = chat.getRoom(name).wait().room
        return room

    def update_room(self):
        if not self.current_room or not self.last_message:
            return
        results = chat.getMessagesAfter(
            self.current_room.name, self.last_message
        ).wait().messages
        if results:
            print('\r', end='')
            new_room = self.current_room.as_builder()
            new_room.messages = list(new_room.messages) + list(results)
            self.current_room = new_room.as_reader()
            for result in results:
                self.print_message(result)
            print(commands.prompt(
                self.current_room.name if self.current_room else None
            ), end='')
            sys.stdout.flush()
            self.last_message = result


if __name__ == '__main__':
    try:
        input = raw_input
    except NameError:
        pass

    client = capnp.TwoPartyClient(SERVER_ADDRESS)
    chat = client.bootstrap().cast_as(Chat)
    commands = Commands()
    command_queue = queue.Queue()
    command_lock = threading.Lock()
    user = User()
    def get_input():
        while True:
            while command_lock.locked():
                time.sleep(.001)
            try:
                command_queue.put(
                    input(commands.prompt(
                        user.current_room.name if user.current_room else None
                    ))
                )
            except EOFError:
                break
    command_thread = threading.Thread(target=get_input)
    command_thread.daemon = True
    quit = False

    print('ChatRoom v0.1')
    print('Commands: {}'.format(', '.join([
        '"%s"' % command for command in commands.list
    ])))
    command_thread.start()

    while not quit:
        command_lock.acquire()

        try:
            command = command_queue.get(False)
        except queue.Empty:
            command = None
            command_lock.release()

        if command:
            try:
                commands.evaluate(command)
            except ValueError as exception:
                print('ERROR: %s' % exception.message)

        user.update_room()

        if command_lock.locked():
            command_lock.release()
            time.sleep(.01)

        if not command_thread.is_alive():
            quit = True
