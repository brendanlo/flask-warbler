from email.utils import collapse_rfc2231_value
import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, flash, redirect, session, g
from flask_debugtoolbar import DebugToolbarExtension
from sqlalchemy.exc import IntegrityError

from forms import UserAddForm, LoginForm, MessageForm, CSRFProtectForm, EditUserProfileForm, LikesForm
from models import db, connect_db, User, Message, MessageLikes

CURR_USER_KEY = "curr_user"
load_dotenv()

app = Flask(__name__)

# Get DB_URI from environ variable (useful for production/testing) or,
# if not set there, use development local db.
app.config['SQLALCHEMY_DATABASE_URI'] = (
    os.environ['DATABASE_URL'].replace("postgres://", "postgresql://"))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False
app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
toolbar = DebugToolbarExtension(app)

connect_db(app)
# db.create_all()


##############################################################################
# User signup/login/logout


@app.before_request
def add_user_to_g():
    """If we're logged in, add curr user to Flask global."""

    add_logout_form()

    if CURR_USER_KEY in session:
        g.user = User.query.get(session[CURR_USER_KEY])

    else:
        g.user = None


def do_login(user):
    """Log in user."""

    session[CURR_USER_KEY] = user.id


def do_logout():
    """Logout user."""

    if CURR_USER_KEY in session:
        del session[CURR_USER_KEY]


def add_logout_form():
    """Before every route, add CSRF-only form to global object."""

    g.csrf_form = CSRFProtectForm()


@app.route('/signup', methods=["GET", "POST"])
def signup():
    """Handle user signup.

    Create new user and add to DB. Redirect to home page.

    If form not valid, present form.

    If the there already is a user with that username: flash message
    and re-present form.
    """

    form = UserAddForm()

    if form.validate_on_submit():
        try:
            user = User.signup(
                username=form.username.data,
                password=form.password.data,
                email=form.email.data,
                image_url=form.image_url.data or User.image_url.default.arg,
            )
            db.session.commit()

        except IntegrityError:
            flash("Username already taken", 'danger')
            return render_template('users/signup.html', form=form)

        do_login(user)

        return redirect("/")

    else:
        return render_template('users/signup.html', form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    """Handle user login."""

    form = LoginForm()

    if form.validate_on_submit():
        user = User.authenticate(form.username.data,
                                 form.password.data)

        if user:
            do_login(user)
            flash(f"Hello, {user.username}!", "success")
            return redirect("/")

        flash("Invalid credentials.", 'danger')

    return render_template('users/login.html', form=form)


@app.post('/logout')
def logout():
    """Handle logout of user."""

    logout_form = g.csrf_form

    if logout_form.validate_on_submit():
        do_logout()

    flash("You logged out!")
    return redirect("/login")


##############################################################################
# General user routes:

@app.get('/users')
def list_users():
    """Page with listing of users.

    Can take a 'q' param in querystring to search by that username.
    """

    search = request.args.get('q')

    if not search:
        users = User.query.all()
    else:
        users = User.query.filter(User.username.like(f"%{search}%")).all()

    return render_template('users/index.html', users=users)


@app.get('/users/<int:user_id>')
def users_show(user_id):
    """Show user profile."""

    user = User.query.get_or_404(user_id)

    user_likes = MessageLikes.query.filter(MessageLikes.user_id==user_id).count()

    return render_template(
        'users/show.html',
        user=user,
        form=g.csrf_form,
        user_likes=user_likes,
        )


@app.get('/users/<int:user_id>/following')
def show_following(user_id):
    """Show list of people this user is following."""


    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user = User.query.get_or_404(user_id)
    user_likes = MessageLikes.query.filter(MessageLikes.user_id==user_id).count()

    return render_template(
        'users/following.html',
        user=user,
        form=g.csrf_form,
        user_likes=user_likes)


@app.get('/users/<int:user_id>/followers')
def users_followers(user_id):
    """Show list of followers of this user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user_likes = MessageLikes.query.filter(MessageLikes.user_id==user_id).count()
    user = User.query.get_or_404(user_id)
    return render_template(
        'users/followers.html',
        user=user,
        form=g.csrf_form,
        user_likes=user_likes)


@app.get('/users/<int:user_id>/likes')
def show_likes(user_id):
    """Show list of messages this user is likes."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user = User.query.get_or_404(user_id)

    return render_template('users/likes.html',
                           user=user, 
                           form=g.csrf_form, 
                           )


@app.post('/users/follow/<int:follow_id>')
def add_follow(follow_id):
    """Add a follow for the currently-logged-in user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    followed_user = User.query.get_or_404(follow_id)
    g.user.following.append(followed_user)
    db.session.commit()

    return redirect(f"/users/{g.user.id}/following")


@app.post('/users/stop-following/<int:follow_id>')
def stop_following(follow_id):
    """Have currently-logged-in-user stop following this user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    followed_user = User.query.get(follow_id)
    g.user.following.remove(followed_user)
    db.session.commit()

    return redirect(f"/users/{g.user.id}/following")


@app.route('/users/profile', methods=["GET", "POST"])
def profile():
    """Update profile for current user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    form = EditUserProfileForm(obj=g.user)

    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        email = form.email.data
        image_url = form.image_url.data
        if image_url == "":
            image_url = "/static/images/default-pic.png"
        header_image_url = form.header_image_url.data
        if header_image_url == "":
            header_image_url = "/static/images/warbler-hero.jpg"
        bio = form.bio.data

        user = User.authenticate(g.user.username, password)

        if user:
            user.username = username
            user.email = email
            user.image_url = image_url
            user.header_image_url = header_image_url
            user.bio = bio

            db.session.commit()

            return redirect(f'/users/{g.user.id}')
        
        else: 
            flash("Wrong Username/Password")
            # so wrong password doesn't lead to redirect to homepage
            # return redirect('/')

    return render_template('/users/edit.html', form=form)


@app.post('/users/delete')
def delete_user():
    """Delete user."""
    
    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    if g.csrf_form.validate_on_submit():
        do_logout()

        Message.query.filter(Message.user_id == g.user.id).delete()
        db.session.delete(g.user)
        db.session.commit()

        return redirect("/signup")


##############################################################################
# Messages routes:

@app.route('/messages/new', methods=["GET", "POST"])
def messages_add():
    """Add a message:

    Show form if GET. If valid, update message and redirect to user page.
    """

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    form = MessageForm()

    if form.validate_on_submit():
        msg = Message(text=form.text.data)
        g.user.messages.append(msg)
        db.session.commit()

        return redirect(f"/users/{g.user.id}")

    return render_template('messages/new.html', form=form)


@app.get('/messages/<int:message_id>')
def messages_show(message_id):
    """Show a message."""

    msg = Message.query.get(message_id)
    return render_template(
        'messages/show.html',
        message=msg,
        form=g.csrf_form,
        )


@app.post('/messages/<int:message_id>/delete')
def messages_destroy(message_id):
    """Delete a message."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    msg = Message.query.get(message_id)
    db.session.delete(msg)
    db.session.commit()

    return redirect(f"/users/{g.user.id}")


##############################################################################
# Homepage and error pages


@app.get('/')
def homepage():
    """Show homepage:

    - anon users: no messages
    - logged in: 100 most recent messages of followed_users
    """

    if g.user:
        
        following_and_self = g.user.following + [g.user]
    
        list_of_ids = [user.id for user in following_and_self]
        
        messages = (Message.query
                    .filter(Message.user_id.in_(list_of_ids))
                    .order_by(Message.timestamp.desc())
                    .limit(100)
                    .all())

        return render_template(
            'home.html',
            messages=messages,
            form=g.csrf_form,
            )

    else:
        return render_template('home-anon.html')
    
##############################################################################
# Liking and Unliking warblers

# NOTE helper functions could be in another file or in part of a class
# rename to like_message
def liking_message(message_id):
    """Liking message and adding it to message_likes table"""
    
    liked = MessageLikes(message_id = message_id, user_id = g.user.id)

    db.session.add(liked)
    
def disliking_message(message_id):
    """Disliking message and removing from message_likes table"""
    
    disliked = MessageLikes.query.get((message_id, g.user.id))
    
    db.session.delete(disliked)
    
@app.post('/users/<int:user_id>/likes')
@app.post('/messages/<int:message_id>')
@app.post('/users/<int:user_id>')
@app.post('/')
def handles_like_unlike(**kwargs):
    """Handles likes and dislikes on warblers with forms and redirects to same page"""
    
    form = LikesForm()

    if form.validate_on_submit():
        
        message_id = form.message_id.data
        page = form.redirect.data
        
        message = Message.query.get(message_id)
        message_user_id = message.user_id
        
        if message_user_id != g.user.id:

            message_likes = MessageLikes.query.get((message_id, g.user.id))
    
            if message_likes:
                disliking_message(message_id)
                db.session.commit()

            else:
                liking_message(message_id)
                db.session.commit()
                   
    return redirect(page)

    
    
# End of Liking and Unliking warblers
##############################################################################


##############################################################################
# Turn off all caching in Flask
#   (useful for dev; in production, this kind of stuff is typically
#   handled elsewhere)
#
# https://stackoverflow.com/questions/34066804/disabling-caching-in-flask

@app.after_request
def add_header(response):
    """Add non-caching headers on every request."""

    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
    response.cache_control.no_store = True
    return response
