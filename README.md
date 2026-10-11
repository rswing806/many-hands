[README (1).md](https://github.com/user-attachments/files/33306744/README.1.md)
# Many Hands

A website where people in a school or neighborhood can find volunteer opportunities, sign up in one click, and keep track of every hour they give.

![Home page](screenshots/home.png)

<!-- Live demo: add your link here once the site is deployed -->

## Features

- Create an account and log in (passwords are hashed, never stored as plain text)
- Browse upcoming events, search by keyword, and filter by category
- Sign up for an event or cancel your sign-up, with a limit on spots per event
- Log hours you gave at other organizations
- Personal dashboard with your total hours and a chart of the last six months
- Admin page to post and delete events (the first account created becomes the admin)
- Form protection against CSRF attacks, and a layout that works on phones

## Built with

Python (Flask), SQLite, HTML, CSS, JavaScript, Chart.js

## Run it on your computer

You need Python 3.9 or newer.

**Windows (PowerShell)**

```
git clone https://github.com/rswing806/many-hands.git
cd many-hands
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

**Mac or Linux**

```
git clone https://github.com/rswing806/many-hands.git
cd many-hands
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in your browser. Sample events are added the first time you run it. Create an account to start; the first account is the admin.

## How it works

- `app.py` holds the whole backend: the routes, the database setup, and the login logic.
- The database (`volunteer.db`) is created automatically with four tables: users, events, signups, and logged hours.
- Pages are built with Flask templates in `templates/`, and styles are in `static/style.css`.
- The dashboard chart gets its data from a small JSON route (`/api/hours`) and draws it with Chart.js.
- Every form includes a hidden token that the server checks, which blocks requests coming from other websites.

## Known limitations

- Hours that volunteers log themselves are not verified by anyone.
- There is no password reset and no email.
- There is a single admin and no separate organizations.

## What I learned

<!-- Write this part yourself, in your own words. Name one or two real problems you ran into
     and how you solved them. Admissions readers care about this section most. -->

## Ideas for next steps

- Let organizers approve hours and mark who attended
- A printable hours report for each volunteer
- Email reminders the day before an event
- Edit events instead of only adding and deleting them

## License

MIT
