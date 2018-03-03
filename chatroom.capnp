@0xfefec1ffd1ff1d03;

interface Chat {
    save @0 (name :Text);
    getAllRooms @4 () -> (rooms :List(Room));
    getRoom @1 (name :Text) -> (room :Room);
    getMessages @2 (name :Text) -> (messages :List(Message));
    sendMessage @3 (room :Room, message :Message);
}

struct Room {
    id @0 :UInt32;
    name @1 :Text;
    messages @2 :List(Message);
}

struct Message {
    id @0 :UInt32;
    author @1 :Text;
    content @2 :Text;
}
