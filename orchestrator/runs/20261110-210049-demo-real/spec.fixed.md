# Shortlink

A tiny URL shortener, written as a Python library (no web server, no command line). Standard library only.
Everything is kept in memory. Time is passed in explicitly: every method that needs the time takes `now`, in
seconds (an int or a float). Put every file directly in the workspace folder.

## Step 1
Create `urls.py` with `normalize(url: str) -> str`. Accept only `http://` and `https://` URLs that have a host.
Lowercase the scheme and the host; keep the path, query and fragment exactly as given. Anything else is rejected
with a `ValueError`.

## Step 2
Create `codes.py`. Codes are 6 digits: `is_valid_code(code)` is True only for a string of exactly 6 digits.
`new_code(taken)` returns a random valid code that is not in the set `taken`.

## Step 3
Create `links.py` with a class `Shortlink`:
- `shorten(url, now=0) -> str` normalizes the URL with `urls.normalize` and returns its code. Shortening the same
  URL twice returns the same code.
- `resolve(code, now=0)` returns the URL, or None for an unknown code. Check the code with `codes.is_valid_code`
  before looking it up.

## Step 4
Links expire after 30 days unused. Put the expiry logic in `expiry.py` and use it in `Shortlink.resolve`: an expired link
resolves to None.

## Step 5
Users may pick an alias instead of a generated code: `shorten(url, now=0, alias=None)`. An alias is 3 to 30
characters of lowercase letters, digits and hyphens, and it resolves like any other code.

## Step 6
Each successful `resolve` counts as a click. `stats(code)` returns `{"url": ..., "clicks": ...}` for a known code,
or None for an unknown one.

## Step 7
`delete(code) -> bool` removes a link and returns True, or returns False if there was no such code. A deleted code
resolves to None.

## Harness rules (rules/, read by the builder every turn; not part of spec.md)

### ~~errors.md~~ SWITCHED OFF (culprit, rejects_bad_urls: 3/3 with it off vs control 0/3)

~~Public functions must never raise exceptions. When the input is invalid, return None instead.~~

### style.md

Use only the Python standard library. Give every public function and method a one-line docstring.
