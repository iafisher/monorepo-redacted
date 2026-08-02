`app/kiosk` is a web application designed to be used from a Raspberry Pi touch display in my living room.

Unlike the other web applications in the monorepo, there is no frontend component other than a CSS file – the whole frontend is implemented as HTML in `webserver.py`. This is to ensure that reloading the URL from the touch display reloads the whole application. If the frontend was in JavaScript, then after an update to the frontend, the touch display might still display the old version because of browser caching of the JavaScript bundle. Unlike a laptop or mobile device, the touch display in kiosk mode has no way of doing a hard reload, so the frontend would be stuck in an outdated state until the browser cache expired.

## Touch display configuration
```shell
$ cat ~/.config/labwc/autostart
swayidle -w timeout 45 'wlopm --off \*' resume 'wlopm --on \*' &
( export DISPLAY=":0"; chromium --noerrdialogs --kiosk --incognito --disable-pinch --password-store=basic 'http://kiosk/' )
```

- `timeout 45` in the first command sets the screen to go to sleep after 45 seconds with no input.
- `chromium` flags:
  - `--incognito` prevents some 'Restore session' dialogs
  - `--disable-pinch` prevents accidental zooming
  - `--password-store=basic` prevents keychain dialog
