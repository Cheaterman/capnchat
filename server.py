import capnp
import glob
import os
import uuid
from chatroom_capnp import Chat, Room


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
    def save(self, room, _context=None, **kwargs):
        loader.persist(room)

    def getAllRooms(self, _context, **kwargs):
        return loader.restore_all()

    def getRoom(self, name, _context, **kwargs):
        return loader.restore(name)

    def getMessages(self, name, _context, **kwargs):
        return self.getRoom(name).messages

    def sendMessage(self, room, message, _context, **kwargs):
        room = loader.restore(room.name)
        new_room = room.as_builder()
        new_room.messages = list(room.messages) + [message]
        self.save(new_room.as_reader())


if __name__ == '__main__':
    loader = RoomLoader()
    server = capnp.TwoPartyServer('*:50000', bootstrap=ChatServer())
    server.run_forever()
