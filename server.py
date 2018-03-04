import capnp
import glob
import os
import uuid
from chatroom_capnp import Chat, Room


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
            room = Room.read(open(savefile_name, 'rb'))
        else:
            print('New room: {}'.format(name))
            room = Room.new_message(
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


class ChatServer(Chat.Server):
    def save(self, room, _context, **kwargs):
        loader.persist(room)

    def getAllRooms(self, _context, **kwargs):
        return loader.restore_all()

    def getRoom(self, name, _context, **kwargs):
        return loader.restore(name)

    def getMessages(self, name, _context, **kwargs):
        return self.getRoom(name, _context).messages

    def getMessagesAfter(self, name, message, _context, **kwargs):
        message_dict = message.to_dict()
        found = False
        results = []
        for message in self.getMessages(name, _context):
            if found:
                results.append(message)
            if(
                not found and
                message.to_dict() == message_dict
            ):
                found = True
        if(
            not results and
            message.to_dict() != message_dict
        ):
            results = list(room.messages)
        return results

    def sendMessage(self, name, message, _context, **kwargs):
        message = message.as_builder()
        message.id = uuid.uuid4().int & 0xFFFFFFFF
        room = self.getRoom(name, _context)
        new_room = room.as_builder()
        new_room.messages = list(room.messages) + [message]
        self.save(new_room.as_reader(), _context)
        return message


if __name__ == '__main__':
    loader = RoomLoader()
    print('Listening on %s' % SERVER_ADDRESS)
    server = capnp.TwoPartyServer(SERVER_ADDRESS, bootstrap=ChatServer())
    server.run_forever()
