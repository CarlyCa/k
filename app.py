from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import os


# Get the directory of the current script
basedir = os.path.abspath(os.path.dirname(__file__))

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "restaurants.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback_key_for_dev')
print("Current working directory:", os.getcwd())

# Initialize database
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# Restaurant model
class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    user = db.relationship('User', backref=db.backref('restaurants', lazy=True))

# MenuItem model
class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # Menu item name
    rating = db.Column(db.Float, nullable=False)  # Menu item rating
    notes = db.Column(db.Text, nullable=True)  # Optional notes for the menu item
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))  # Link to the restaurant
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Link to the user who rated it

    restaurant = db.relationship('Restaurant', backref=db.backref('menu_items', lazy=True))
    user = db.relationship('User', backref=db.backref('menu_items', lazy=True))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize the database
def setup_database():
    with app.app_context():
        if not os.path.exists('restaurants.db'):
            db.create_all()
            print("Database initialized successfully")

@app.route('/')
@login_required
def index():
    search_query = request.args.get('search', '')
    if search_query:
        restaurants = Restaurant.query.filter(
            Restaurant.user_id == current_user.id,
            Restaurant.name.ilike(f'%{search_query}%')
        ).all()
    else:
        restaurants = Restaurant.query.filter_by(user_id=current_user.id).all()
    return render_template('index.html', restaurants=restaurants)

@app.route('/add', methods=['POST'])
@login_required
def add_restaurant():
    name = request.form['name']
    rating = float(request.form['rating'])
    new_restaurant = Restaurant(name=name, rating=rating, user_id=current_user.id)
    db.session.add(new_restaurant)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/restaurant/<int:restaurant_id>')
@login_required
def view_menu_items(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    menu_items = MenuItem.query.filter_by(restaurant_id=restaurant_id).all()
    return render_template('menu_items.html', restaurant=restaurant, menu_items=menu_items)

@app.route('/restaurant/<int:restaurant_id>/add_menu_item', methods=['POST'])
@login_required
def add_menu_item(restaurant_id):
    name = request.form['name']
    rating = float(request.form['rating'])
    notes = request.form.get('notes', '')  # Optional notes
    new_menu_item = MenuItem(name=name, rating=rating, notes=notes, restaurant_id=restaurant_id, user_id=current_user.id)
    db.session.add(new_menu_item)
    db.session.commit()
    return redirect(url_for('view_menu_items', restaurant_id=restaurant_id))


@app.route('/menu_item/<int:menu_item_id>/rate', methods=['POST'])
@login_required
def rate_menu_item(menu_item_id):
    menu_item = MenuItem.query.get_or_404(menu_item_id)

    # Ensure the current user is allowed to rate (optional check)
    if menu_item.user_id != current_user.id:
        flash("You can only rate your own menu items.")
        return redirect(url_for('view_menu_items', restaurant_id=menu_item.restaurant_id))

    # Update the rating
    new_rating = float(request.form['rating'])
    menu_item.rating = new_rating
    db.session.commit()

    flash("Rating updated successfully!")
    return redirect(url_for('view_menu_items', restaurant_id=menu_item.restaurant_id))

@app.route('/menu_item/<int:menu_item_id>/update_notes', methods=['POST'])
@login_required
def update_notes(menu_item_id):
    menu_item = MenuItem.query.get_or_404(menu_item_id)
    if menu_item.user_id != current_user.id:
        flash("You can only update notes for your own menu items.")
        return redirect(url_for('view_menu_items', restaurant_id=menu_item.restaurant_id))

    notes = request.form.get('notes', '')
    menu_item.notes = notes
    db.session.commit()

    flash("Notes updated successfully!")
    return redirect(url_for('view_menu_items', restaurant_id=menu_item.restaurant_id))



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose a different one.')
            return redirect(url_for('register'))
        new_user = User(username=username, password=password)  # Note: Use hashing in production
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:  # Note: Use hashing in production
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid credentials. Please try again.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('login'))

if __name__ == '__main__':
    setup_database()
    app.run(debug=True)
