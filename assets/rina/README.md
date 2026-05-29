# Rina Asset Folder

This folder is the project-local replacement point for Rina desktop pet assets.

Known source images from the older API test project:

```text
E:\API_test\RinaChanBoard\img\Rina_bot.jpg
E:\API_test\RinaChanBoard\img\Rina_UI.jpeg
E:\API_test\RinaChanBoard\img\Rina_UI.ico
E:\API_test\RinaChanBoard\img\Rina_user.jpg
```

Current primary placeholder:

```text
Rina_bot_cutout.png
```

Current copied files:

```text
E:\OurDeskPet\assets\rina\Rina_bot.jpg
E:\OurDeskPet\assets\rina\Rina_bot_cutout.png
E:\OurDeskPet\assets\rina\Rina_UI.ico
```

M1 uses `Rina_bot_cutout.png`, a generated transparent-background version of `Rina_bot.jpg`. The original JPG remains the source file.

Future A1 state-specific assets may be organized like this:

```text
assets\rina
  source\
  processed\
  sprites\
  icons\
```

Suggested state image names for A1:

```text
rina_idle.png
rina_follow.png
rina_dragging.png
rina_sleep.png
rina_talk.png
rina_notification.png
```

Missing state images should fall back to the default idle/placeholder image.
