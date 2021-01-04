# Checkout modes

There are two primary modes of operation when checking out sources from Fossil: incremental and full.

## Incremental mode

An incremental checkout uses an existing checkout and simply updates it to the new revision:

    fossil revert
    fossil update <revision>

The revert command ensures that changes to any version controlled files are reverted before updating to the new revision. This means that all files under version control will be as checked in.

Any non-versioned files existing in the checkout are left as is. This means that object files from previous builds can be reused for incremental builds.

## Full mode

A full checkout does lot leave any non-versioned files behind from previous builds. There are different methods for ensuring this.

### Clean method

The most gentle method relies on `fossil clean`:

    fossil revert
    fossil clean --verily
    fossil update <revision>

This is the fastest since most versioned files can stay in place.

### Copy method

This will completely delete the working directory and check out a fresh copy from the repository:

    rmdir <workdir>
    fossil open --workdir <workdir> --empty
    fossil update <revision>

The Fossil repository is maintained outside the working directory, and it is reused between checkouts.

### Clobber method

Clobber everything and clone the repository anew:

    rm <repo>
    rmdir <workdir>
    fossil clone <repourl> <repo>
    fossil open --workdir <workdir> --empty
    fossil update <revision>

This is the slowest method with the most network traffic.


# JSON API

The JSON API `GET /json/timeline/checkin?files=1` is better than RSS because it includes names of changed files, and it requires less clever parsing to extract tags etc.

Doesn't work with `--repolist` in version 2.13 and earlier. Fixed in 2.14.

Requires `h` capabilities which the `nobody` user normally doesn't have.

1. Give `h` capabilities to `nobody`, or
2. Log in as `anonymous`, or
3. Create proper account for buildbot.

See [Defense Against Spiders](https://fossil-scm.org/home/doc/trunk/www/antibot.wiki) for why the `nobody` user should not have Hyperlinks capabilities.

# Fossil auth

Fossil logins are probably only required for the JSON poller. RSS polling and cloning for checkouts normally don't require auth.

[Response codes](https://fossil-scm.org/home/doc/trunk/www/json-api/conventions.md#result-codes) will indicate when auth is required.

## Login with user+password

POST to `/json/login` with form parameters `name=` and `password=`. Get back JSON payload:

```json
   "payload" : {
      "authToken" : "49B18223XXXXXXXXXXXXXXXXXXXXXXXXX8992375B/xxxxxxxxxfb39b/jolesen",
      "name" : "jolesen",
      "capabilities" : "s",
      "loginCookieName" : "fossil-xxxxxxxxxfb39b"
   }
```

The response also contains a corresponding `Set-Cookie` header.

In subsequent requests, either pass the cookie `$loginCookieName=$authToken`, or pass a query parameter `authToken`.

## Login as anonymous

Request the password with `GET /json/anonymousPassword` to receive:

```json
   "payload" : {
      "password" : "0e06d5c8",
      "seed" : 1057836951
   },
```

Then proceed to `POST /json/login` as above with an additional `anonymousSeed=$seed` form parameter.

## Implementation

The `treq` package doesn't have a session which keeps track of cookies, and we also can't get the cookies from a response in a portable way.

Solution: Build a `loginCookie = { loginCookieName: authToken }` dict after logging in, and pass that with `get(cookies=loginCookie)` on every request. We can also persist loginCookie.

