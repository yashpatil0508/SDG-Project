import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app import app, db
from models import Department, Employee, Payment

def generate_mock_kaggle_dataset(csv_path, num_records=250):
    print(f"Generating mock HR dataset with {num_records} records...")
    
    np.random.seed(42) # For reproducible results
    
    first_names = ['James', 'Mary', 'John', 'Patricia', 'Robert', 'Jennifer', 'Michael', 'Linda', 'William', 'Elizabeth', 'David', 'Barbara', 'Richard', 'Susan', 'Joseph', 'Jessica', 'Thomas', 'Sarah', 'Charles', 'Karen', 'Christopher', 'Nancy', 'Daniel', 'Lisa', 'Matthew', 'Betty', 'Anthony', 'Margaret', 'Mark', 'Sandra', 'Yash', 'Priya', 'Raj', 'Anita', 'Wei', 'Li', 'Carlos', 'Maria']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Patel', 'Sharma', 'Chen', 'Wang']
    
    departments = ['Engineering', 'Human Resources', 'Sales', 'Marketing', 'Finance', 'Customer Support', 'Product Management', 'Legal']
    
    data = []
    
    # Help generate random dates within last 5 years
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5*365)
    
    manager_index = np.random.randint(0, num_records)
    
    for i in range(num_records):
        f_name = np.random.choice(first_names)
        l_name = np.random.choice(last_names)
        emp_id = f"EMP{str(1000 + i).zfill(4)}"
        email = f"{f_name.lower()}.{l_name.lower()}{np.random.randint(1, 99)}@company.com"
        dept = np.random.choice(departments)
        role = 'Manager' if i == manager_index else 'Employee'
        
        # Salary bands based on role
        if role == 'Admin':
            salary = np.random.randint(120000, 180000)
        elif role == 'Manager':
            salary = np.random.randint(90000, 140000)
        else:
            salary = np.random.randint(50000, 100000)
            
        # Random join date
        random_days = np.random.randint(0, (end_date - start_date).days)
        join_date = (start_date + timedelta(days=random_days)).strftime('%Y-%m-%d')
        
        perf_score = round(np.random.uniform(2.5, 5.0), 1)
        status = np.random.choice(['Active'] * 90 + ['On Leave'] * 5 + ['Terminated'] * 5)
        
        data.append([emp_id, f_name, l_name, email, role, dept, salary, join_date, perf_score, status])
        
    df = pd.DataFrame(data, columns=['Employee_ID', 'First_Name', 'Last_Name', 'Email', 'Role', 'Department', 'Salary', 'Join_Date', 'Performance_Score', 'Status'])
    df.drop_duplicates(subset=['Email'], inplace=True) # Ensure unique emails
    df.to_csv(csv_path, index=False)
    print(f"Saved dataset to {csv_path}")
    return df

def import_csv_to_db(csv_path):
    print(f"Reading {csv_path}...")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Clear existing non-user data if needed to prevent duplicates during re-runs
        db.session.query(Employee).delete()
        db.session.commit()
        
        for index, row in df.iterrows():
            dept_name = str(row['Department'])
            
            # Find or create department
            dept = Department.query.filter_by(name=dept_name).first()
            if not dept:
                dept = Department(name=dept_name)
                db.session.add(dept)
                db.session.commit()
            
            emp_id = str(row['Employee_ID'])
            
            # Parse date safely
            try:
                join_date = datetime.strptime(str(row['Join_Date']), '%Y-%m-%d').date()
            except ValueError:
                join_date = datetime.now().date()
                
            # Create employee
            emp = Employee(
                employee_id=emp_id,
                first_name=str(row['First_Name']),
                last_name=str(row['Last_Name']),
                email=str(row['Email']),
                role=str(row['Role']),
                department_id=dept.id,
                salary=int(row['Salary']) if pd.notna(row['Salary']) else None,
                join_date=join_date,
                performance_score=float(row['Performance_Score']) if pd.notna(row['Performance_Score']) else None,
                status=str(row['Status'])
            )
            db.session.add(emp)
            db.session.commit() # commit to get emp.id
            
            # Generate mock payments (e.g., past 3-12 months)
            import random
            months = random.randint(3, 12)
            payment_amount = int(row['Salary']) / 12 if pd.notna(row['Salary']) else 5000
            for m in range(months):
                pay_date = datetime.now() - timedelta(days=30*m)
                payment = Payment(
                    employee_id=emp.id,
                    amount=payment_amount,
                    payment_date=pay_date.date(),
                    status='Paid',
                    description=f"Monthly Salary for {pay_date.strftime('%B %Y')}"
                )
                db.session.add(payment)
                
        db.session.commit()
        print(f"Successfully processed and imported {len(df)} employees to database.")

if __name__ == "__main__":
    csv_file = "kaggle_hr_dataset.csv" 
    
    # Always generate fresh for this demo or use if exists, let's just generate to ensure it works
    generate_mock_kaggle_dataset(csv_file, 250)
    import_csv_to_db(csv_file)
