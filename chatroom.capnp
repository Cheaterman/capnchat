@0xfefec1ffd1ff1d03;

interface Server {
    login @0 (client :Client, name :Text) -> (id :UInt32);
    list @1 (client_id :UInt32) -> (rooms :List(ChatRoom));
    join @2 (client_id :UInt32, name :Text) -> (room :ChatRoom);
    nick @3 (client_id :UInt32, name :Text);

    struct ChatRoom {
        id @0 :UInt32;
        name @1 :Text;
        room @2 :Room;
    }

    struct SavedRoom {
        id @0 :UInt32;
        name @1 :Text;
        messages @2 :List(Message);
    }
}

interface Client {
    receive @0 (message :Message);
}

interface Room {
    get @0 () -> (messages :List(Message));
    send @1 (message :Message) -> (id :UInt32);
    names @2 () -> (users :List(Client));
}

struct Message {
    id @0 :UInt32;
    author @1 :Text;
    content @2 :Text;
}
