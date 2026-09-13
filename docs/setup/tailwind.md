# Tailwind CSS build (standalone CLI)

NextTable has no Node.js/npm toolchain (see docs/plan.md's "keep it simple"
principle). Tailwind CSS is compiled using the **Tailwind standalone CLI** -
a single self-contained binary, not an npm package.

## One-time setup: download the CLI binary

Download the binary for your platform from the Tailwind CSS GitHub releases
and put it at `bin/tailwindcss` (gitignored - each machine downloads its own
copy):

```sh
curl -sL \
  https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 \
  -o bin/tailwindcss
chmod +x bin/tailwindcss
```

(Use `tailwindcss-macos-arm64`, `tailwindcss-macos-x64`, or
`tailwindcss-windows-x64.exe` instead of `tailwindcss-linux-x64` on other
platforms - see the release assets at
https://github.com/tailwindlabs/tailwindcss/releases/latest.)

This project was built and tested against Tailwind CLI **v4.3.3**.

## Source files

- `static/src/input.css` - the Tailwind entry file (`@import "tailwindcss";`
  plus `@config` pointing at `tailwind.config.js`).
- `tailwind.config.js` (repo root) - scopes class scanning to
  `templates/**/*.html`.

## Build command

Run from the repo root whenever templates change and you need to refresh the
compiled CSS:

```sh
./bin/tailwindcss -i ./static/src/input.css -o ./static/css/app.css --minify
```

This writes the compiled stylesheet to `static/css/app.css`, inside the
`STATICFILES_DIRS` source directory (`static/`) configured in
`config/settings.py`. `templates/base.html` links to it via
`{% static 'css/app.css' %}`, so it is served directly by `manage.py
runserver` in development and copied into `STATIC_ROOT` by `manage.py
collectstatic` for deployment.

The compiled `static/css/app.css` is committed to the repository so the app
runs out of the box without requiring every clone/CI run to have the
Tailwind binary available; re-run the build command above and commit the
result after editing templates or `tailwind.config.js`.
