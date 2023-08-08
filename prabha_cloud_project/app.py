from flask import Flask, request, session, redirect, url_for, send_from_directory,render_template
import os
import boto3
import botocore.exceptions
import uuid
import json
import configparser
from botocore.client import Config
import time
import threading
from flask_sqlalchemy import SQLAlchemy
import threading
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import boto3

# AWS configuration
aws_region = "us-east-1"
aws_access_key = "AKIAXSO3LTF7DZKXMOYT"
aws_secret_key = "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"
bucket = "prabhapuppalacloud123"
lambdafunc = "prabhalamdafunc"
database = "prabhapuppalatable"
secret = "12345678"
bucketurl = f"https://{bucket}.s3.amazonaws.com/"

# Flask app setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.secret_key = "your_secret_key"
db = SQLAlchemy(app)
#db.create_all()

# Define User class
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

# AWS setup
aws_instance = boto3.Session(
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name=aws_region
)

s3_instance = aws_instance.client('s3')
db_instance = aws_instance.resource('dynamodb')
lambda_instance = aws_instance.client('lambda')

# Route Handlers
def verify_user_session(session):
    if 'email' in session:
        user_email = session['email']
        user = User.query.filter_by(email=user_email).first()

        if user:
            return send_from_directory('templates', 'email_sender.html')

    return send_from_directory('templates', 'signin.html')

def verify_user_login(session, email, password):
    user = User.query.filter_by(email=email, password=password).first()

    if user:
        session['email'] = user.email
        return redirect(url_for('file_upload_route'))
    else:
        session.pop('email', None)
        return redirect(url_for('indexpage'))

def save_file_to_s3(file, s3_client):
    filename = file.filename
    s3_client.upload_fileobj(file, bucket, filename)

def create_database_record(table_name, db_resource, items):
    table = db_resource.Table(table_name)
    print(table.name)
    table.put_item(Item=items)

# Function to generate a presigned URL and track link click
def generate_and_track_presigned_url(filename):
    s3_client = boto3.client(
        's3',
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
        config=Config(signature_version='s3v4')
    )

    presigned_url = s3_client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': bucket,
            'Key': filename
        },
        ExpiresIn=100000
    )

    return presigned_url

def invoke_lambda_function(lambda_client,  payload,lambda_func):
    lambda_client.invoke(
        FunctionName=lambda_func,
        InvocationType='Event', 
        Payload=payload
    )
    print("Lambda function called")
    
@app.route('/', methods=['GET'])
def home_page():
    return verify_user_session(session)

@app.route('/register', methods=['GET', 'POST'])
def user_registration():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return "User with this email already exists. Please use a different email."
        
        new_user = User(username=username, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('home_page'))
    
    return render_template('signup.html')

@app.route('/login', methods=['POST'])
def user_login_post():
    email = request.form['email']
    password = request.form['password']
    return verify_user_login(session, email, password)

@app.route('/logout', methods=['GET'])
def user_logout():
    session.pop('email', None)
    return redirect(url_for('home_page')) 

@app.route('/file-upload', methods=['GET'])
def file_upload_route():
    if 'email' in session:
        return send_from_directory('templates', 'email_sender.html')
    else:
        return redirect(url_for('home_page')) 
    
@app.route('/upload-file', methods=['POST'])
def upload_file_post():
    if 'email' in session:
        user_email = session['email']
        logged_user = User.query.filter_by(email=user_email).first()

        if logged_user:
            if 'file' in request.files:
                uploaded_file = request.files['file']
                if uploaded_file.filename:
                    recipient_emails = [request.form.get(f'email{i}') for i in range(1, 6) if request.form.get(f'email{i}')]

                    try:
                        filename = uploaded_file.filename
                        save_file_to_s3(uploaded_file, s3_instance)
                        s3_url = f"https://{bucket}.s3.amazonaws.com/{filename}"
                        new_record = {
                            'id': str(uuid.uuid4()),
                            'filename': filename,
                            'bucketurl': s3_url,
                            'Mails': recipient_emails
                        }
                        create_database_record(database, db_instance, new_record)
                        download_url = generate_and_track_presigned_url(filename)
                        
                        for email in recipient_emails: 
                            payload = json.dumps({
                                'FileName': filename,
                                'Tomail': email,
                                'url': download_url
                            }).encode('utf-8')
                            invoke_lambda_function(lambda_instance, payload, lambdafunc)
                            
                        return '<h1 style="text-align: center;">File Upload Successful and Email sent to the user</h1>'
                    except botocore.exceptions.ClientError as e:
                        return {'error': str(e)}
            return '<h2>File Upload Error</h2>'


        else:
            return redirect(url_for('home_page'))
    else:
        return redirect(url_for('home_page'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        app.run(port=8000,debug=True)
