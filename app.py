from flask import (Flask, render_template, redirect, url_for,
                   request, flash, jsonify, send_from_directory)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'clone-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clone.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ── MODELS ────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id              = db.Column(db.Integer, primary_key=True)
    username        = db.Column(db.String(50), unique=True, nullable=False)
    email           = db.Column(db.String(120), unique=True, nullable=False)
    full_name       = db.Column(db.String(100), default='')
    bio             = db.Column(db.Text, default='')
    avatar_url      = db.Column(db.String(300), default='')
    password_hash   = db.Column(db.String(200), nullable=False)
    is_private      = db.Column(db.Boolean, default=False)
    is_active_shown = db.Column(db.Boolean, default=True)
    last_seen       = db.Column(db.DateTime, default=datetime.utcnow)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def followers_count(self):
        return Follow.query.filter_by(following_id=self.id).count()

    def following_count(self):
        return Follow.query.filter_by(follower_id=self.id).count()

    def is_following(self, user):
        return Follow.query.filter_by(
            follower_id=self.id, following_id=user.id).first() is not None

    def is_blocked_by(self, user):
        return Block.query.filter_by(
            blocker_id=user.id, blocked_id=self.id).first() is not None

    def has_blocked(self, user):
        return Block.query.filter_by(
            blocker_id=self.id, blocked_id=user.id).first() is not None

    def is_online(self):
        if not self.is_active_shown:
            return False
        diff = datetime.utcnow() - (self.last_seen or datetime.utcnow())
        return diff.total_seconds() < 300


class Follow(db.Model):
    __tablename__ = 'follows'
    id           = db.Column(db.Integer, primary_key=True)
    follower_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    following_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)


class Block(db.Model):
    __tablename__ = 'blocks'
    id         = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Post(db.Model):
    __tablename__ = 'posts'
    id         = db.Column(db.Integer, primary_key=True)
    owner_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    image_url  = db.Column(db.String(300), nullable=False)
    caption    = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner      = db.relationship('User', backref='posts', lazy=True)
    likes      = db.relationship('Like', backref='post', lazy=True, cascade='all, delete')
    comments   = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete')

    def likes_count(self):
        return Like.query.filter_by(post_id=self.id).count()

    def is_liked_by(self, user):
        return Like.query.filter_by(
            post_id=self.id, user_id=user.id).first() is not None

    def is_saved_by(self, user):
        return SavedPost.query.filter_by(
            post_id=self.id, user_id=user.id).first() is not None


class Like(db.Model):
    __tablename__ = 'likes'
    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)


class Comment(db.Model):
    __tablename__ = 'comments'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id    = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    text       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user       = db.relationship('User', foreign_keys=[user_id])


class SavedPost(db.Model):
    __tablename__ = 'saved_posts'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id    = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Story(db.Model):
    __tablename__ = 'stories'
    id            = db.Column(db.Integer, primary_key=True)
    owner_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    media_url     = db.Column(db.String(300), nullable=False)
    expires_at    = db.Column(db.DateTime, nullable=False)
    close_friends = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    owner         = db.relationship('User', backref='stories', lazy=True)
    views         = db.relationship('StoryView', backref='story', lazy=True, cascade='all, delete')

    def is_active(self):
        return datetime.utcnow() < self.expires_at


class StoryView(db.Model):
    __tablename__ = 'story_views'
    id              = db.Column(db.Integer, primary_key=True)
    story_id        = db.Column(db.Integer, db.ForeignKey('stories.id'), nullable=False)
    viewer_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    took_screenshot = db.Column(db.Boolean, default=False)
    viewed_at       = db.Column(db.DateTime, default=datetime.utcnow)
    viewer          = db.relationship('User', foreign_keys=[viewer_id])


class CloseFriend(db.Model):
    __tablename__ = 'close_friends'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    friend_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Message(db.Model):
    __tablename__ = 'messages'
    id          = db.Column(db.Integer, primary_key=True)
    sender_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text        = db.Column(db.Text, nullable=False)
    is_read     = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    sender      = db.relationship('User', foreign_keys=[sender_id])
    receiver    = db.relationship('User', foreign_keys=[receiver_id])


class Notification(db.Model):
    __tablename__ = 'notifications'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    actor_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type       = db.Column(db.String(30), nullable=False)
    entity_id  = db.Column(db.Integer, nullable=True)
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    actor      = db.relationship('User', foreign_keys=[actor_id])


# ── LOGIN ─────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def add_notification(user_id, actor_id, notif_type, entity_id=None):
    n = Notification(user_id=user_id, actor_id=actor_id,
                     type=notif_type, entity_id=entity_id)
    db.session.add(n)
    db.session.commit()


def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()


# ── AUTH ──────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('feed'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('feed'))
    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        email     = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password  = request.form.get('password', '')
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        user = User(username=username, email=email, full_name=full_name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Welcome to Clone! 🎉', 'success')
        return redirect(url_for('feed'))
    return render_template('auth.html', mode='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('feed'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('feed'))
        flash('Wrong username or password', 'error')
    return render_template('auth.html', mode='login')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ── FEED ──────────────────────────────────────────────

@app.route('/feed')
@login_required
def feed():
    update_last_seen()
    following_ids = [
        f.following_id
        for f in Follow.query.filter_by(follower_id=current_user.id).all()
    ]
    following_ids.append(current_user.id)
    blocked_ids = [
        b.blocked_id for b in Block.query.filter_by(blocker_id=current_user.id).all()
    ]
    posts = Post.query.filter(
        Post.owner_id.in_(following_ids),
        ~Post.owner_id.in_(blocked_ids)
    ).order_by(Post.created_at.desc()).limit(30).all()

    # Only show stories from close friends or public stories
    cf_ids = [
        c.friend_id for c in CloseFriend.query.filter_by(user_id=current_user.id).all()
    ]
    stories = Story.query.filter(
        Story.owner_id.in_(following_ids),
        Story.expires_at > datetime.utcnow(),
        ~Story.owner_id.in_(blocked_ids)
    ).order_by(Story.created_at.desc()).all()

    visible_stories = []
    for s in stories:
        if s.close_friends and s.owner_id not in cf_ids and s.owner_id != current_user.id:
            continue
        visible_stories.append(s)

    return render_template('feed.html', posts=posts, stories=visible_stories)


# ── POSTS ─────────────────────────────────────────────

@app.route('/post/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        caption = request.form.get('caption', '')
        file    = request.files.get('image')
        if not file or not allowed_file(file.filename):
            flash('Please upload a valid image', 'error')
            return redirect(url_for('create_post'))
        ext      = file.filename.rsplit('.', 1)[1].lower()
        filename = f"post_{current_user.id}_{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        post = Post(owner_id=current_user.id,
                    image_url=filename, caption=caption)
        db.session.add(post)
        db.session.commit()
        flash('Post shared! 📸', 'success')
        return redirect(url_for('feed'))
    return render_template('create_post.html')


@app.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({'status': 'error', 'count': 0}), 404
    existing = Like.query.filter_by(
        user_id=current_user.id, post_id=post_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'status': 'unliked', 'count': post.likes_count()})
    db.session.add(Like(user_id=current_user.id, post_id=post_id))
    db.session.commit()
    if post.owner_id != current_user.id:
        add_notification(post.owner_id, current_user.id, 'like', post_id)
    return jsonify({'status': 'liked', 'count': post.likes_count()})


@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = db.session.get(Post, post_id)
    if not post:
        return jsonify({'error': 'Not found'}), 404
    text = request.form.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Empty'}), 400
    comment = Comment(user_id=current_user.id, post_id=post_id, text=text)
    db.session.add(comment)
    db.session.commit()
    if post.owner_id != current_user.id:
        add_notification(post.owner_id, current_user.id, 'comment', post_id)
    return jsonify({'id': comment.id, 'text': comment.text,
                    'username': current_user.username})


@app.route('/post/<int:post_id>/save', methods=['POST'])
@login_required
def save_post(post_id):
    existing = SavedPost.query.filter_by(
        user_id=current_user.id, post_id=post_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'status': 'unsaved'})
    db.session.add(SavedPost(user_id=current_user.id, post_id=post_id))
    db.session.commit()
    return jsonify({'status': 'saved'})


@app.route('/saved')
@login_required
def saved_posts():
    saves = SavedPost.query.filter_by(
        user_id=current_user.id
    ).order_by(SavedPost.created_at.desc()).all()
    posts = [db.session.get(Post, s.post_id) for s in saves]
    posts = [p for p in posts if p]
    return render_template('saved.html', posts=posts)


# ── STORIES ───────────────────────────────────────────

@app.route('/story/create', methods=['GET', 'POST'])
@login_required
def create_story():
    if request.method == 'POST':
        file = request.files.get('media')
        if not file or not allowed_file(file.filename):
            flash('Invalid file', 'error')
            return redirect(url_for('create_story'))
        close_friends = request.form.get('close_friends') == 'on'
        ext      = file.filename.rsplit('.', 1)[1].lower()
        filename = f"story_{current_user.id}_{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        story = Story(owner_id=current_user.id, media_url=filename,
                      expires_at=datetime.utcnow() + timedelta(hours=24),
                      close_friends=close_friends)
        db.session.add(story)
        db.session.commit()
        flash('Story posted! 🌟', 'success')
        return redirect(url_for('feed'))
    return render_template('create_story.html')


@app.route('/story/<int:story_id>/view', methods=['POST'])
@login_required
def view_story(story_id):
    story = db.session.get(Story, story_id)
    if not story:
        return jsonify({'status': 'error'}), 404
    data       = request.get_json() or {}
    screenshot = data.get('screenshot', False)
    existing   = StoryView.query.filter_by(
        story_id=story_id, viewer_id=current_user.id).first()
    if not existing:
        view = StoryView(story_id=story_id, viewer_id=current_user.id,
                         took_screenshot=screenshot)
        db.session.add(view)
        db.session.commit()
        if story.owner_id != current_user.id:
            notif_type = 'screenshot' if screenshot else 'seen'
            add_notification(story.owner_id, current_user.id, notif_type, story_id)
    return jsonify({'status': 'recorded'})


@app.route('/story/<int:story_id>/viewers')
@login_required
def story_viewers(story_id):
    story = db.session.get(Story, story_id)
    if not story or story.owner_id != current_user.id:
        return redirect(url_for('feed'))
    views = StoryView.query.filter_by(story_id=story_id).all()
    return render_template('story_viewers.html', story=story, views=views)


# ── FOLLOW & BLOCK ────────────────────────────────────

@app.route('/user/<int:user_id>/follow', methods=['POST'])
@login_required
def follow_user(user_id):
    if user_id == current_user.id:
        return jsonify({'status': 'error'})
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({'status': 'error'})
    existing = Follow.query.filter_by(
        follower_id=current_user.id, following_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'status': 'unfollowed'})
    db.session.add(Follow(follower_id=current_user.id, following_id=user_id))
    db.session.commit()
    add_notification(user_id, current_user.id, 'follow')
    return jsonify({'status': 'followed'})


@app.route('/user/<int:user_id>/block', methods=['POST'])
@login_required
def block_user(user_id):
    if user_id == current_user.id:
        return jsonify({'status': 'error'})
    existing = Block.query.filter_by(
        blocker_id=current_user.id, blocked_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'status': 'unblocked'})
    # Remove follow relationship both ways
    Follow.query.filter_by(
        follower_id=current_user.id, following_id=user_id).delete()
    Follow.query.filter_by(
        follower_id=user_id, following_id=current_user.id).delete()
    db.session.add(Block(blocker_id=current_user.id, blocked_id=user_id))
    db.session.commit()
    return jsonify({'status': 'blocked'})


# ── PROFILE ───────────────────────────────────────────

@app.route('/user/<username>')
@login_required
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user.has_blocked(current_user):
        flash('This account is not available', 'error')
        return redirect(url_for('explore'))
    is_blocked    = current_user.has_blocked(user)
    is_following  = current_user.is_following(user)
    can_see_posts = (not user.is_private) or is_following or (user.id == current_user.id)
    posts = Post.query.filter_by(
        owner_id=user.id).order_by(Post.created_at.desc()).all() if can_see_posts else []
    followers = Follow.query.filter_by(following_id=user.id).all()
    following = Follow.query.filter_by(follower_id=user.id).all()
    return render_template('user_profile.html', user=user, posts=posts,
                           is_following=is_following, is_blocked=is_blocked,
                           can_see_posts=can_see_posts,
                           followers=followers, following=following)


@app.route('/profile')
@login_required
def profile():
    posts = Post.query.filter_by(
        owner_id=current_user.id).order_by(Post.created_at.desc()).all()
    followers = Follow.query.filter_by(following_id=current_user.id).all()
    following = Follow.query.filter_by(follower_id=current_user.id).all()
    return render_template('profile.html', user=current_user,
                           posts=posts, followers=followers, following=following)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name', '')
        current_user.bio       = request.form.get('bio', '')
        avatar = request.files.get('avatar')
        if avatar and allowed_file(avatar.filename):
            ext      = avatar.filename.rsplit('.', 1)[1].lower()
            filename = f"avatar_{current_user.id}_{uuid.uuid4().hex}.{ext}"
            avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.avatar_url = filename
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('profile'))
    return render_template('edit_profile.html')


@app.route('/followers/<int:user_id>')
@login_required
def followers_list(user_id):
    user      = db.session.get(User, user_id)
    followers = Follow.query.filter_by(following_id=user_id).all()
    people    = [db.session.get(User, f.follower_id) for f in followers]
    return render_template('follow_list.html', user=user,
                           people=people, list_type='Followers')


@app.route('/following/<int:user_id>')
@login_required
def following_list(user_id):
    user      = db.session.get(User, user_id)
    following = Follow.query.filter_by(follower_id=user_id).all()
    people    = [db.session.get(User, f.following_id) for f in following]
    return render_template('follow_list.html', user=user,
                           people=people, list_type='Following')


# ── CLOSE FRIENDS ─────────────────────────────────────

@app.route('/close-friends')
@login_required
def close_friends():
    following = Follow.query.filter_by(follower_id=current_user.id).all()
    friends   = [db.session.get(User, f.following_id) for f in following]
    cf_ids    = [
        c.friend_id for c in CloseFriend.query.filter_by(
            user_id=current_user.id).all()
    ]
    return render_template('close_friends.html', friends=friends, cf_ids=cf_ids)


@app.route('/close-friends/<int:friend_id>/toggle', methods=['POST'])
@login_required
def toggle_close_friend(friend_id):
    existing = CloseFriend.query.filter_by(
        user_id=current_user.id, friend_id=friend_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'status': 'removed'})
    db.session.add(CloseFriend(user_id=current_user.id, friend_id=friend_id))
    db.session.commit()
    return jsonify({'status': 'added'})


# ── SETTINGS ──────────────────────────────────────────

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'privacy':
            current_user.is_private      = request.form.get('is_private') == 'on'
            current_user.is_active_shown = request.form.get('is_active_shown') == 'on'
            db.session.commit()
            flash('Privacy settings saved!', 'success')
        elif action == 'password':
            old_pw  = request.form.get('old_password', '')
            new_pw  = request.form.get('new_password', '')
            if not current_user.check_password(old_pw):
                flash('Current password is incorrect', 'error')
            elif len(new_pw) < 6:
                flash('New password must be at least 6 characters', 'error')
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash('Password changed!', 'success')
        elif action == 'delete':
            confirm = request.form.get('confirm_delete', '')
            if confirm == current_user.username:
                logout_user()
                db.session.delete(current_user)
                db.session.commit()
                flash('Account deleted', 'success')
                return redirect(url_for('login'))
            else:
                flash('Username did not match', 'error')
        return redirect(url_for('settings'))
    blocked = Block.query.filter_by(blocker_id=current_user.id).all()
    blocked_users = [db.session.get(User, b.blocked_id) for b in blocked]
    return render_template('settings.html', blocked_users=blocked_users)


# ── MESSAGES ──────────────────────────────────────────

@app.route('/messages')
@login_required
def messages():
    update_last_seen()
    sent     = Message.query.filter_by(sender_id=current_user.id).all()
    received = Message.query.filter_by(receiver_id=current_user.id).all()
    partners = {}
    for m in sent + received:
        other_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
        if other_id not in partners:
            other  = db.session.get(User, other_id)
            unread = Message.query.filter_by(
                sender_id=other_id,
                receiver_id=current_user.id,
                is_read=False).count()
            partners[other_id] = {
                'user': other, 'last_msg': m.text, 'unread': unread}
    return render_template('messages.html', conversations=list(partners.values()))


@app.route('/messages/<int:user_id>', methods=['GET', 'POST'])
@login_required
def conversation(user_id):
    other = db.session.get(User, user_id)
    if not other:
        return redirect(url_for('messages'))
    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        if text:
            db.session.add(Message(sender_id=current_user.id,
                                   receiver_id=user_id, text=text))
            db.session.commit()
        return redirect(url_for('conversation', user_id=user_id))
    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) &
         (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) &
         (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at).all()
    for m in msgs:
        if m.receiver_id == current_user.id and not m.is_read:
            m.is_read = True
    db.session.commit()
    return render_template('conversation.html', other=other, messages=msgs)


# ── NOTIFICATIONS ─────────────────────────────────────

@app.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).limit(50).all()
    for n in notifs:
        n.is_read = True
    db.session.commit()
    return render_template('notifications.html', notifications=notifs)


@app.route('/notifications/count')
@login_required
def notif_count():
    count = Notification.query.filter_by(
        user_id=current_user.id, is_read=False).count()
    return jsonify({'count': count})


# ── CHATBOT ───────────────────────────────────────────

@app.route('/chatbot', methods=['GET', 'POST'])
@login_required
def chatbot():
    reply = None
    if request.method == 'POST':
        msg = request.form.get('message', '').lower()
        if 'caption' in msg:
            reply = 'Try: "Chasing sunsets and good vibes ✨ #GoldenHour"'
        elif 'hashtag' in msg:
            reply = '#Photography #Explore #VisualStory #GoldenHour #InstaDaily'
        elif 'edit' in msg or 'filter' in msg:
            reply = 'Boost Contrast +10, Clarity +5, warm tone. Use Lightroom or Snapseed!'
        elif 'grow' in msg:
            reply = 'Post daily, use 8-10 hashtags, reply to every comment, post at 7-9 PM!'
        elif 'story' in msg:
            reply = 'Post 3-7 stories/day, use polls and question stickers!'
        elif 'reel' in msg:
            reply = 'Keep Reels under 30 seconds, use trending audio!'
        elif 'bio' in msg:
            reply = 'Use 1-2 emojis, your niche keyword, and a call-to-action!'
        elif 'private' in msg:
            reply = 'Go to Settings → Privacy to make your account private!'
        else:
            reply = 'Ask me about captions, hashtags, editing, growing or stories! 📸'
    return render_template('chatbot.html', reply=reply)


# ── EXPLORE & DISCOVER ────────────────────────────────

@app.route('/explore')
@login_required
def explore():
    query = request.args.get('q', '').strip()
    users = []
    posts = []
    if query:
        blocked_ids = [b.blocked_id for b in Block.query.filter_by(
            blocker_id=current_user.id).all()]
        users = User.query.filter(
            User.username.ilike(f'%{query}%'),
            User.id != current_user.id,
            ~User.id.in_(blocked_ids)
        ).limit(10).all()
        posts = Post.query.filter(
            Post.caption.ilike(f'%{query}%')
        ).order_by(Post.created_at.desc()).limit(30).all()
    else:
        posts = Post.query.order_by(Post.created_at.desc()).limit(60).all()
    return render_template('explore.html', posts=posts, users=users, query=query)


@app.route('/discover')
@login_required
def discover():
    following_ids = [
        f.following_id for f in Follow.query.filter_by(
            follower_id=current_user.id).all()
    ]
    following_ids.append(current_user.id)
    blocked_ids = [b.blocked_id for b in Block.query.filter_by(
        blocker_id=current_user.id).all()]
    people = User.query.filter(
        ~User.id.in_(following_ids),
        ~User.id.in_(blocked_ids)
    ).order_by(User.created_at.desc()).limit(20).all()
    return render_template('discover.html', people=people)


# ── UPLOADS ───────────────────────────────────────────

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


if __name__ == "__main__":
    import os
    with app.app_context():
        db.create_all()
        print("✅ Database ready!")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))