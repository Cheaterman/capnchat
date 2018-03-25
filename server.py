#!/usr/bin/env python

import capnp
import functools
import glob
import os
import uuid
from chatroom_capnp import (
    Message as Capnp_Message,
    Login as Capnp_Login,
    Client as Capnp_Client,
    ChatServer as Capnp_ChatServer,
)


SERVER_ADDRESS = '0.0.0.0:50000'


class RoomLoader(object):
    def __init__(self):
        self.loaded_rooms = {}

    def persist(self, room):
        print('Saving room: {}'.format(room.name))
        self.loaded_rooms[room.name] = room
        with open(self.savefile_name(room.name), 'wb') as savefile:
            room.write(savefile)

    def restore(self, name):
        if name in self.loaded_rooms:
            return self.loaded_rooms[name]
        savefile_name = self.savefile_name(name)
        if os.path.exists(savefile_name):
            print('Loading room: {}'.format(name))
            room = Capnp_ChatServer.SavedRoom.read(open(savefile_name, 'rb'))
        else:
            print('New room: {}'.format(name))
            room = Capnp_ChatServer.SavedRoom.new_message(
                id=uuid.uuid4().int & 0xFFFFFFFF,
                name=name,
                messages=[],
            )
        self.loaded_rooms[name] = room
        return room

    def restore_all(self):
        results = []
        for savefile_name in glob.glob(self.savefile_name('*')):
            results.append(self.restore(savefile_name.rsplit('.', 2)[0]))
        return results

    @staticmethod
    def savefile_name(name):
        assert name
        return name + '.chatroom.sav'


class Room(Capnp_ChatServer.Room.Server):
    def __init__(self, chatroom, server):
        self.chatroom = chatroom
        self.server = server

    def get(self, _context, **kwargs):
        return self.chatroom.messages

    def send(self, message, _context, **kwargs):
        message = message.as_builder()
        chatroom = self.chatroom
        chatroom.messages.append(message)
        self.server.save_room(chatroom.name)

        promises = []
        for client in chatroom.users:
            if client.name == message.author:
                continue
            promises.append(client.send(message))

        return capnp.join_promises(promises)

    def names(self, _context, **kwargs):
        return self.chatroom.users


class ChatRoom(object):
    def __init__(self, **kwargs):
        if 'room' in kwargs:
            room = kwargs.pop('room')
            id, name, messages = (
                room.id, room.name, room.messages
            )
        elif 'id' in kwargs and 'name' in kwargs and 'messages' in kwargs:
            id, name, messages = (
                kwargs.pop('id'), kwargs.pop('name'), kwargs.pop('messages')
            )
        else:
            raise TypeError(
                "__init__() missing 1 required keyword argument: 'room'; "
                "or 3 required keyword arguments: 'id', 'name', 'messages'"
            )
        if 'server' not in kwargs:
            raise TypeError(
                "__init__() missing 1 required keyword argument: 'server'"
            )
        self.id = id
        self.name = name
        self.messages = [
            Capnp_Message.new_message(
                author=message.author,
                content=message.content,
            )
            for message in messages
        ]
        self.users = []
        self.room = Room(chatroom=self, server=kwargs['server'])

    def join(self, client):
        if self not in client.joined_rooms:
            client.joined_rooms.append(self)

        if client not in self.users:
            self.users.append(client)


class Client(object):
    def __init__(self, client, name, handle):
        self.client = client
        self.name = name
        self._chat_handle = handle
        self.joined_rooms = []

    def send(self, message):
        return self._chat_handle.receive(message)


class ChatServer(Capnp_ChatServer.Server):
    def __init__(self, client):
        self.client = client

    def list(self, _context, **kwargs):
        return list(server.rooms.keys())

    def join(self, name, _context, **kwargs):
        chatroom = server.load_room(name)
        chatroom.join(self.client)
        return chatroom.room

    def nick(self, name, _context, **kwargs):
        if not server.validate_nickname(name):
            raise ValueError(
                'Invalid username (maybe someone is already using it?)'
            )
        self.client.name = name


class Login(Capnp_Login.Server):
    def login(self, client, name, _context, **kwargs):
        if not name or not server.validate_login(self.client, name):
            raise ValueError(
                'Invalid username (maybe someone is already using it?)'
            )

        print('New user login from %s' % name)
        return server.login(client, name, self)

    def on_connect(self, client):
        print('New connection from %s:%d' % client)
        self.client = client

    def on_disconnect(self):
        print('Client %s (%s:%d) disconnected.' % (
            (server.clients[self.client].name,) + self.client
        ))
        server.logout(self.client)


class LoginHandle(Capnp_Login.LoginHandle.Server):
    def __init__(self, login):
        self.login = login

    def __del__(self):
        self.login.on_disconnect()


class CapnChat(object):
    def __init__(self):
        self.clients = {}
        self.loader = loader = RoomLoader()
        self.rooms = {
            room.name: ChatRoom(
                room=room,
                server=self,
            )
            for room in loader.restore_all()
        }

    def load_room(self, name):
        if name not in self.rooms:
            self.rooms[name] = ChatRoom(
                room=self.loader.restore(name),
                server=self
            )
        return self.rooms[name]

    def save_room(self, name):
        room = self.rooms[name]
        self.loader.persist(Capnp_ChatServer.SavedRoom.new_message(
            id=room.id,
            name=room.name,
            messages=[
                Capnp_ChatServer.SavedMessage.new_message(
                    author=message.author,
                    content=message.content,
                )
                for message in room.messages
            ]
        ))

    def validate_login(self, client, name):
        if(
            client in [user.client for user in self.clients.values()] or
            not self.validate_nickname(name)
        ):
            return False
        return True

    def validate_nickname(self, name):
        if name in [user.name for user in self.clients.values()]:
            return False
        return True

    def login(self, client, name, login):
        client_handle = Client(login.client, name, client)
        self.clients[login.client] = client_handle

        return ChatServer(client=client_handle), LoginHandle(login=login)

    def logout(self, client):
        client_handle = self.clients[client]
        for room in client_handle.joined_rooms:
            room.users.remove(client_handle)
        del self.clients[client]


if __name__ == '__main__':
    print('Listening on %s' % SERVER_ADDRESS)
    server = CapnChat()
    capnp_server = capnp.TwoPartyServer(SERVER_ADDRESS, bootstrap=Login)
    capnp_server.run_forever()
