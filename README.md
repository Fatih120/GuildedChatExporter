# GuildedChatExporter
Exports your dearest chats from Guilded to a file, along with downloading all attachments from said channel.

https://colab.research.google.com/drive/1IfJnB3LWPMb55nRL7bjbulOKTHxPEvHT?usp=sharing

Currently being done in google colab and is unfortunately made with AI, standalone/desktop versions maybe eventually

# how to use rn:
- make a bot for your server, get an auth token for it and paste this into the API_KEY field
- right click the channel you want to archive and click "copy channel id", paste this into the CHANNEL_ID field
  - make sure Settings > Advanced > Developer Mode is on if you don't see the command
  - alternatively copy the channel link, the channel ID is https://www.guilded.gg/<name>/groups/<groupid>/channels/<THIS-LONG-FIELD-HERE>
- Run the cells in colab using the top left button, do the same with the next ones to link your Google Drive (ignore the Check Server one for now), fetch all messages in the server, save the chat to a file, and then save attachments
- copy off your exported files from guildedchatexporter on your googledrive and it should be good to go

![firefox_2024_0606-205534](https://github.com/Fatih120/GuildedChatExporter/assets/18276369/d99f675c-a0e8-44ea-9a16-a9cf3826b59f)


## todo
- handling of those weird ? url queries and possible renaming of attachments
- HTML exporter like in https://github.com/nulldg/DiscordChatExporterPlus
- do this automatically for a whole group/server
- fetch user roles and colours and pfps and fix names
- system notifications

# Contact and Support

https://www.guilded.gg/i/2ZnlDm92
https://www.guilded.gg/MoF
