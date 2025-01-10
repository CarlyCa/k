from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import os


# Get the directory of the current script
basedir = os.path.abspath(os.path.dirname(__file__))

# Initialize Flask app
app = Flask(__name__)

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://restaurant_6pmd_user:y93Jnqu7DdutMMvCD3ufENzJRWRBrQOU@dpg-cu0ms53tq21c73ctcekg-a.oregon-postgres.render.com/restaurant_6pmd')
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback_key_for_dev')

# Add the print statement here
print(f"Connected to database: {app.config['SQLALCHEMY_DATABASE_URI']}")

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
# Association table for shared restaurants
restaurant_shares = db.Table('restaurant_shares',
    db.Column('restaurant_id', db.Integer, db.ForeignKey('restaurant.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    user = db.relationship('User', backref=db.backref('restaurants', lazy=True))
    shared_with = db.relationship('User', secondary=restaurant_shares, 
                                backref=db.backref('shared_restaurants', lazy=True))

    @property
    def rating(self):
        menu_items = MenuItem.query.filter_by(restaurant_id=self.id).all()
        if not menu_items:
            return 0.0
        return sum(item.rating for item in menu_items) / len(menu_items)

# MenuItem model
class MenuItemRevision(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'))
    rating = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    notes = db.Column(db.Text, nullable=True)

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    restaurant = db.relationship('Restaurant', backref=db.backref('menu_items', lazy=True))
    user = db.relationship('User', backref=db.backref('menu_items', lazy=True))
    revisions = db.relationship('MenuItemRevision', backref='menu_item', order_by='MenuItemRevision.created_at.desc()')

    @property
    def rating(self):
        latest_revision = MenuItemRevision.query.filter_by(menu_item_id=self.id).order_by(MenuItemRevision.created_at.desc()).first()
        return latest_revision.rating if latest_revision else 0.0

    @property
    def notes(self):
        latest_revision = MenuItemRevision.query.filter_by(menu_item_id=self.id).order_by(MenuItemRevision.created_at.desc()).first()
        return latest_revision.notes if latest_revision else None


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize the database
def setup_database():
    with app.app_context():
        db.create_all()
        print("Database initialized successfully")


@app.route('/share/<int:restaurant_id>', methods=['POST'])
@login_required
def share_restaurant(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    if restaurant.user_id != current_user.id:
        flash('You can only share restaurants you own.')
        return redirect(url_for('index'))
    
    username = request.form['username']
    user_to_share_with = User.query.filter_by(username=username).first()
    
    if not user_to_share_with:
        flash('User not found.')
        return redirect(url_for('index'))
        
    if user_to_share_with in restaurant.shared_with:
        flash('Restaurant already shared with this user.')
        return redirect(url_for('index'))
        
    restaurant.shared_with.append(user_to_share_with)
    db.session.commit()
    flash(f'Restaurant shared with {username}')
    return redirect(url_for('index'))

@app.route('/')
@login_required
def index():
    search_query = request.args.get('search', '')
    view = request.args.get('view', 'my')  # 'my' or 'shared'
    
    if view == 'shared':
        restaurants = current_user.shared_restaurants
        if search_query:
            # Search in shared restaurants and their menu items
            restaurants = [
                r for r in restaurants 
                if search_query.lower() in r.name.lower() or
                any(search_query.lower() in item.name.lower() for item in r.menu_items)
            ]
    else:
        if search_query:
            # Search in user's restaurants
            restaurant_name_matches = Restaurant.query.filter(
                Restaurant.user_id == current_user.id,
                Restaurant.name.ilike(f'%{search_query}%')
            )
            
            # Search in menu items
            menu_item_matches = Restaurant.query.join(MenuItem).filter(
                Restaurant.user_id == current_user.id,
                MenuItem.name.ilike(f'%{search_query}%')
            )
            
            # Combine results
            restaurants = list(set(restaurant_name_matches.all() + menu_item_matches.all()))
        else:
            restaurants = Restaurant.query.filter_by(user_id=current_user.id).all()
    
    return render_template('index.html', restaurants=restaurants, view=view)

@app.route('/add', methods=['POST'])
@login_required
def add_restaurant():
    name = request.form['name']
    new_restaurant = Restaurant(name=name, user_id=current_user.id)
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
    notes = request.form.get('notes', '')
    
    new_menu_item = MenuItem(name=name, restaurant_id=restaurant_id, user_id=current_user.id)
    db.session.add(new_menu_item)
    db.session.flush()  # This ensures new_menu_item gets its ID
    
    initial_revision = MenuItemRevision(menu_item_id=new_menu_item.id, rating=rating, notes=notes)
    db.session.add(initial_revision)
    db.session.commit()
    
    return redirect(url_for('view_menu_items', restaurant_id=restaurant_id))


@app.route('/menu_item/<int:menu_item_id>/rate', methods=['POST'])
@login_required
def rate_menu_item(menu_item_id):
    menu_item = MenuItem.query.get_or_404(menu_item_id)

    if menu_item.user_id != current_user.id:
        flash("You can only rate your own menu items.")
        return redirect(url_for('view_menu_items', restaurant_id=menu_item.restaurant_id))

    new_rating = float(request.form['rating'])
    notes = request.form.get('notes', '')
    
    new_revision = MenuItemRevision(
        menu_item_id=menu_item.id,
        rating=new_rating,
        notes=notes
    )
    db.session.add(new_revision)
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
    # Get the current rating from the latest revision
    current_rating = menu_item.rating
    
    # Create a new revision with the updated notes but same rating
    new_revision = MenuItemRevision(
        menu_item_id=menu_item.id,
        rating=current_rating,
        notes=notes
    )
    db.session.add(new_revision)
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
