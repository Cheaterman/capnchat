import capnp
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
            room.as_builder().write(savefile)

    def persist_all(self):
        for room in self.loaded_rooms.values():
            self.persist(room)

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
            ).as_reader()
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
    def __init__(self, chatroom):
        self.chatroom = chatroom

    def get(self, _context, **kwargs):
        return self.chatroom.messages

    def send(self, message, _context, **kwargs):
        message = message.as_builder()
        self.chatroom.messages.append(message)
        for client in self.chatroom.users:
            client.send(message).wait()

    def names(self, _context, **kwargs):
        return self.chatroom.users


class ChatRoom(object):
    def __init__(self, **kwargs):
        if 'room' in kwargs:
            room = kwargs.pop('room').as_builder()
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
        self.id = id
        self.name = name
        self.messages = list(messages)
        self.users = []
        self.room = Room(chatroom=self)

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
        print('Sending message to %s (%d): <%s> %s' % (
            self.name,
            self.id,
            message.author,
            message.content,
        ))
        return self._client.receive(message)


class Server(Capnp_Server.Server):
    def __init__(self, **kwargs):
        self.clients = {}
        self.rooms = {}
        self.loader = loader = RoomLoader()
        loader.restore_all()


    def get_room(self, name):
        if name not in self.rooms:
            self.rooms[name] = ChatRoom(room=self.loader.restore(name))
        return self.rooms[name]

    def login(self, client, name, _context, **kwargs):
        if not name or name in [user.name for user in self.clients.values()]:
            return

        client = Client(name, client)

        print('Got new client %s (%d)' % (name, client.id))

        self.clients[client.id] = client
        return client.id

    class login_required(object):
        def __new__(cls, func):
            def _func(self, client_id, **kwargs):
                if client_id not in self.clients:
                    return
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


if __name__ == '__main__':
    print('Listening on %s' % SERVER_ADDRESS)
    server = capnp.TwoPartyServer(SERVER_ADDRESS, bootstrap=Server())
    server.run_forever()
