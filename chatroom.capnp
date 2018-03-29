@0xfefec1ffd1ff1d03;

struct Message {
    author @0 :Text;
    content @1 :Text;
}

interface Login {
    login @0 (client :Client, name :Text) -> (server :ChatServer, handle :LoginHandle);

    interface LoginHandle {}
}

interface Client {
    receive @0 (message :Message);
}

interface ChatServer {
    list @0 () -> (rooms :List(Text));
    join @1 (name :Text) -> (room :Room);
    nick @2 (name :Text);

    interface Room {
        get @0 () -> (messages :List(Message));
        send @1 (text :Text);
        names @2 () -> (users :List(Text));
    }

    struct SavedRoom {
        id @0 :UInt32;
        name @1 :Text;
        messages @2 :List(SavedMessage);
    }

    struct SavedMessage {
        id @0 :UInt32;
        author @1 :Text;
        content @2 :Text;
    }
}
