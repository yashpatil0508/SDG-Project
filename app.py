import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Department, Employee, ActivityLog, Payment
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev_secret_key_12345'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///directory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def dashboard():
    total_employees = Employee.query.count()
    total_departments = Department.query.count()
    
    # Aggregations for dashboard charts
    departments = Department.query.all()
    dept_stats = []
    for dept in departments:
        count = Employee.query.filter_by(department_id=dept.id).count()
        if count > 0:
            dept_stats.append({'name': dept.name, 'count': count})
            
    recent_joins = Employee.query.order_by(Employee.join_date.desc()).limit(5).all()
    
    return render_template('dashboard.html', 
                           total_employees=total_employees, 
                           total_departments=total_departments,
                           dept_stats=dept_stats,
                           recent_joins=recent_joins)

@app.route('/employees')
@login_required
def employees():
    dept_filter = request.args.get('department')
    role_filter = request.args.get('role')
    search_query = request.args.get('q', '').strip()
    
    query = Employee.query
    
    if search_query:
        query = query.filter(
            db.or_(
                Employee.first_name.ilike(f'%{search_query}%'),
                Employee.last_name.ilike(f'%{search_query}%'),
                Employee.employee_id.ilike(f'%{search_query}%')
            )
        )
        
    if dept_filter:
        query = query.filter_by(department_id=dept_filter)
        
    if role_filter:
        query = query.filter(Employee.role.ilike(role_filter))
        
    # Sort — default to 'recent' so newly added employees appear first
    sort_by = request.args.get('sort', 'recent')
    if sort_by == 'name':
        query = query.order_by(Employee.first_name.asc(), Employee.last_name.asc())
    else:  # 'recent' or default
        query = query.order_by(Employee.id.desc())
        
    # Pagination
    page = request.args.get('page', 1, type=int)
    pagination = query.paginate(page=page, per_page=20, error_out=False)
    employee_list = pagination.items
    departments = Department.query.order_by(Department.name).all()
    
    return render_template('employees.html', 
                           employees=employee_list, 
                           departments=departments,
                           current_dept=dept_filter,
                           current_role=role_filter,
                           search_query=search_query,
                           pagination=pagination,
                           current_sort=sort_by)

@app.route('/employee/<int:id>')
@login_required
def employee_detail(id):
    employee = Employee.query.get_or_404(id)
    
    # Log access
    log = ActivityLog(user_id=current_user.id, action='view_employee', details=f'Viewed employee {employee.employee_id}')
    db.session.add(log)
    db.session.commit()
    
    is_manager_or_admin = current_user.role in ['admin', 'manager']
    
    payments = Payment.query.filter_by(employee_id=id).order_by(Payment.payment_date.desc()).limit(10).all() if is_manager_or_admin else []
    
    return render_template('employee_detail.html', employee=employee, show_sensitive=is_manager_or_admin, payments=payments)

@app.route('/employee/add', methods=['GET', 'POST'])
@login_required
def add_employee():
    if current_user.role not in ['admin', 'manager']:
        flash('Unauthorized access. Only Managers and Admins can add employees.', 'danger')
        return redirect(url_for('employees'))
        
    if request.method == 'POST':
        try:
            emp_id = request.form.get('employee_id')
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            role = request.form.get('role', 'Employee')
            department_id = request.form.get('department_id')
            salary_str = request.form.get('salary', '')
            salary = int(salary_str) if salary_str.isdigit() else None
            join_date_str = request.form.get('join_date')
            status = request.form.get('status', 'Active')
            
            # Validate required
            if not all([emp_id, first_name, last_name, email, department_id, join_date_str]):
                flash('Please fill out all required fields.', 'warning')
                return redirect(url_for('add_employee'))
                
            # Date parse
            join_date = datetime.strptime(join_date_str, '%Y-%m-%d').date()
            
            # Check unique constraints
            if Employee.query.filter_by(employee_id=emp_id).first():
                flash('Employee ID already exists.', 'warning')
                return redirect(url_for('add_employee'))
            if Employee.query.filter_by(email=email).first():
                flash('Email already registered to another employee.', 'warning')
                return redirect(url_for('add_employee'))
            
            new_emp = Employee(
                employee_id=emp_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                role=role,
                department_id=department_id,
                salary=salary,
                join_date=join_date,
                status=status
            )
            
            db.session.add(new_emp)
            db.session.commit()
            
            # Log action
            log = ActivityLog(user_id=current_user.id, action='add_employee', details=f'Added new employee {emp_id}')
            db.session.add(log)
            db.session.commit()
            
            flash('New employee successfully added!', 'success')
            return redirect(url_for('employee_detail', id=new_emp.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding employee: {str(e)}', 'danger')
            
    departments = Department.query.order_by(Department.name).all()
    return render_template('add_employee.html', departments=departments)

@app.route('/payments')
@login_required
def payments():
    if current_user.role not in ['admin', 'manager']:
        flash('Unauthorized access to payment records.', 'danger')
        return redirect(url_for('dashboard'))
        
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '').strip()
    
    query = Payment.query.join(Employee)
    
    if search_query:
        query = query.filter(
            db.or_(
                Employee.first_name.ilike(f'%{search_query}%'),
                Employee.last_name.ilike(f'%{search_query}%'),
                Employee.employee_id.ilike(f'%{search_query}%')
            )
        )
        
    payments_paginated = query.order_by(Payment.payment_date.desc()).paginate(page=page, per_page=20, error_out=False)
    
    return render_template('payments.html', payments=payments_paginated.items, pagination=payments_paginated, search_query=search_query)


@app.route('/employee/<int:id>/add_payment', methods=['GET', 'POST'])
@login_required
def add_payment(id):
    if current_user.role not in ['admin', 'manager']:
        flash('Unauthorized access. Only Managers and Admins can record payments.', 'danger')
        return redirect(url_for('employees'))
        
    employee = Employee.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount'))
            payment_date_str = request.form.get('payment_date')
            description = request.form.get('description')
            status = request.form.get('status', 'Paid')
            
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
            
            new_payment = Payment(
                employee_id=employee.id,
                amount=amount,
                payment_date=payment_date,
                status=status,
                description=description
            )
            
            db.session.add(new_payment)
            db.session.commit()
            
            # Log action
            log = ActivityLog(user_id=current_user.id, action='add_payment', details=f'Recorded payment of ${amount} for employee {employee.employee_id}')
            db.session.add(log)
            db.session.commit()
            
            flash(f'Payment record for {employee.first_name} {employee.last_name} successfully added!', 'success')
            return redirect(url_for('employee_detail', id=employee.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error recording payment: {str(e)}', 'danger')
            
    today = datetime.now()
    return render_template('add_payment.html', 
                           employee=employee, 
                           today_date=today.strftime('%Y-%m-%d'),
                           today_month_year=today.strftime('%B %Y'))

@app.route('/manage_users')
@login_required
def manage_users():
    if current_user.role != 'admin':
        flash('Unauthorized access. Only System Admins can manage users.', 'danger')
        return redirect(url_for('dashboard'))
        
    users = User.query.order_by(User.id.desc()).all()
    return render_template('manage_users.html', users=users)

@app.route('/update_user_role/<int:user_id>', methods=['POST'])
@login_required
def update_user_role(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))
        
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    
    # Prevent admin from downgrading themselves if they are the only admin
    if user.id == current_user.id and new_role != 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            flash('Cannot downgrade the only admin account.', 'danger')
            return redirect(url_for('manage_users'))
            
    if new_role in ['admin', 'manager', 'employee']:
        user.role = new_role
        
        # Log action
        log = ActivityLog(user_id=current_user.id, action='update_role', details=f'Changed role for {user.email} to {new_role}')
        db.session.add(log)
        db.session.commit()
        
        flash(f"User {user.name}'s role updated to {new_role}.", 'success')
        
    return redirect(url_for('manage_users'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not all([name, email, password, confirm_password]):
            flash('Please fill out all fields.', 'warning')
            return redirect(url_for('register'))
            
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))
            
        # Check if user exists
        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
            
        # Create user
        hashed_password = generate_password_hash(password)
        new_user = User(name=name, email=email, password=hashed_password, role='employee')
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            log = ActivityLog(user_id=user.id, action='login', details='User login')
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        # Avoid overriding models with duplicate definitions if using interactive prompts
        from models import db, User, Department, Employee, ActivityLog, Payment
        from datetime import datetime
        
        db.create_all()
        # Seed an admin user if it doesn't exist
        if not User.query.filter_by(email='admin@company.com').first():
            admin_user = User(
                name='System Admin',
                email='admin@company.com',
                password=generate_password_hash('admin123'),
                role='admin'
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Default User created: admin@company.com / admin123 (Role: admin)")
            
        # Seed a manager user
        if not User.query.filter_by(email='manager@company.com').first():
            manager_user = User(
                name='HR Manager',
                email='manager@company.com',
                password=generate_password_hash('manager123'),
                role='manager'
            )
            db.session.add(manager_user)
            db.session.commit()
            print("Default User created: manager@company.com / manager123 (Role: manager)")
            
        # Seed a regular employee user
        if not User.query.filter_by(email='employee@company.com').first():
            emp_user = User(
                name='Standard User',
                email='employee@company.com',
                password=generate_password_hash('employee123'),
                role='employee'
            )
            db.session.add(emp_user)
            db.session.commit()
            print("Default User created: employee@company.com / employee123 (Role: employee)")

    app.run(debug=True, port=5000)
