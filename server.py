#!/usr/bin/env python

import capnp
import functools
import glob
import os
import uuid
from chatroom_capnp import (
    Client as Capnp_Client,
    Server as Capnp_Server,
    Room as Capnp_Room,
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
            room = Capnp_Server.SavedRoom.read(open(savefile_name, 'rb'))
        else:
            print('New room: {}'.format(name))
            room = Capnp_Server.SavedRoom.new_message(
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


class Room(Capnp_Room.Server):
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
        self.messages = list(messages)
        self.users = []
        self.room = Room(chatroom=self, server=kwargs['server'])

    def as_message(self):
        return Capnp_Server.ChatRoom.new_message(
            id=self.id,
            name=self.name,
            room=self.room,
        )


class Client(object):
    def __init__(self, name, client):
        self.id = uuid.uuid4().int & 0xFFFFFFFF
        self.name = name
        self._client = client
        self.joined_rooms = []

    def send(self, message):
        return self._client.receive(message)


class Handle(Capnp_Server.LoginHandle.Server):
    def __init__(self, client, server):
        self.client = client
        self.server = server

    def __del__(self):
        self.server.on_disconnect(self.client)


class Server(Capnp_Server.Server):
    def __init__(self, **kwargs):
        self.clients = {}
        self.rooms = {}
        self.loader = loader = RoomLoader()
        loader.restore_all()

    def get_room(self, name):
        if name not in self.rooms:
            self.rooms[name] = ChatRoom(
                room=self.loader.restore(name),
                server=self
            )
        return self.rooms[name]

    def save_room(self, name):
        room = self.rooms[name]
        self.loader.persist(Capnp_Server.SavedRoom.new_message(
            id=room.id,
            name=room.name,
            messages=room.messages,
        ))

    def login(self, client, name, _context, **kwargs):
        if not name or name in [user.name for user in self.clients.values()]:
            raise ValueError(
                'Invalid username (maybe someone is already using it?)'
            )

        client = Client(name, client)

        print('Got new client %s (%d)' % (name, client.id))

        self.clients[client.id] = client
        return client.id, Handle(client=client, server=self)

    class login_required(object):
        def __new__(cls, func):
            def _func(self, client_id, **kwargs):
                if client_id not in self.clients:
                    raise ValueError('This client ID does not exist.')
                return func(self, client_id, **kwargs)
            return _func

    @login_required
    def list(self, client_id, _context, **kwargs):
        return [
            self.get_room(saved_room.name).as_message()
            for saved_room in self.loader.restore_all()
        ]

    @login_required
    def join(self, client_id, name, _context, **kwargs):
        chatroom = self.get_room(name)
        proxy_client = self.clients[client_id]

        if chatroom not in proxy_client.joined_rooms:
            proxy_client.joined_rooms.append(chatroom)

        if proxy_client not in chatroom.users:
            chatroom.users.append(proxy_client)

        return chatroom.as_message()

    @login_required
    def nick(self, client_id, name, _context, **kwargs):
        if not name:
            return

        self.clients[client_id].name = name

    def on_disconnect(self, client):
        for room in client.joined_rooms:
            room.users.remove(client)
        del self.clients[client.id]
        print('Client %s (%d) disconnected.' % (client.name, client.id))


if __name__ == '__main__':
    print('Listening on %s' % SERVER_ADDRESS)
    capnp_server = capnp.TwoPartyServer(SERVER_ADDRESS, bootstrap=Server())
    capnp_server.run_forever()
