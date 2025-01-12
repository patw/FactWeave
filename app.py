# Basic flask stuff for building http APIs and rendering html templates
from flask import Flask, render_template, redirect, url_for, request, session

# Bootstrap integration with flask so we can make pretty pages
from flask_bootstrap import Bootstrap

# Flask forms integrations which save insane amounts of time
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, TextAreaField
from wtforms.validators import DataRequired

# Basic python stuff
import os
import json
import functools
import requests
import datetime

# Mongo stuff
import pymongo
from bson import ObjectId

# Use local models with the OpenAI library and a custom baseurl
from openai import OpenAI

# Nice way to load environment variables for deployments
from dotenv import load_dotenv
load_dotenv()

# Connect to mongo using environment variables
client = pymongo.MongoClient(os.environ["MONGO_CON"])
db = client[os.environ["MONGO_DB"]]
col = db["posts"]

# Create the Flask app object
app = Flask(__name__)

# Session key
app.config['SECRET_KEY'] = os.environ["SECRET_KEY"]

# Site path for Hugo, can be any site you want to drop MD files into though
site_path = os.environ["CONTENT"]

# Get some defaults from the config file
DEFAULT_SYSTEM = os.environ["DEFAULT_SYSTEM"]
DEFAULT_PROMPT = os.environ["DEFAULT_PROMPT"]
DEFAULT_STYLE = os.environ["DEFAULT_STYLE"]
DEFAULT_TAGS = os.environ["DEFAULT_TAGS"]
DEFAULT_CATEGORY = os.environ["DEFAULT_CATEGORY"]

# Hugo header string
hugo_header = """
+++
title = '{title}'
date = '{date}'
draft = false
tags = {tags}
categories = {categories}
+++

"""

# User Auth
users_string = os.environ["USERS"]
users = json.loads(users_string)

# Load the llm model config
with open("model.json", 'r',  encoding='utf-8') as file:
    llm_config = json.load(file)

# Load the embedder config
with open("embedder.json", 'r',  encoding='utf-8') as file:
    embedder = json.load(file)

# Make it pretty because I can't :(
Bootstrap(app)

# Function to call the text embedder
def embed(text):
    response = requests.get(embedder["embedding_endpoint"], params={"text":text, "instruction": "Represent this text for retrieval:" }, headers={"accept": "application/json"})
    vector_embedding = response.json()
    return vector_embedding

# Call llm using the llm configuration
def llm_local(prompt, system_message, temperature):
    client = OpenAI(api_key=llm_config["api_key"], base_url=llm_config["base_url"])
    messages=[{"role": "system", "content": system_message},{"role": "user", "content": prompt}]
    response = client.chat.completions.create(model=llm_config["model"], temperature=temperature, messages=messages)
    return response.choices[0].message.content

# Search the facts semantically
def search_posts(prompt, candidates = 100, limit = 5, score_cut = 0.89):

    # Get the embedding for the prompt first
    vector = embed(prompt)

    # Build the Atlas vector search aggregation
    vector_search_agg = [
        {
            "$vectorSearch": { 
                "index": "default",
                "path": "fact_embedding",
                "queryVector": vector,
                "numCandidates": candidates, 
                "limit": limit
            }
        },
        {
            "$project": {
                "subject": 1,
                "facts": 1,
                "style": 1,
                "post": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        },
        {
            "$match": {
                "score": { "$gte": score_cut }
            }
        }
    ]

    # Connect to chunks, run query, return results
    posts = col.aggregate(vector_search_agg)
    return posts

# Blog post edit form for facts and ouput
class BlogPostForm(FlaskForm):
    subject = StringField('Subject or Topic', validators=[DataRequired()])
    facts = TextAreaField('Facts (one per line)', validators=[DataRequired()])
    style = StringField('Post Style/Tone', validators=[DataRequired()])
    tags = StringField('Tags (comma separated)', validators=[DataRequired()])
    categories = StringField('Categories (comma separated)', validators=[DataRequired()])
    post_date = StringField('Post Date', validators=[DataRequired()])
    post = TextAreaField('Post (leave blank to AI generate)')
    submit = SubmitField('Save')

# Search form for blog posts or facts
class SearchForm(FlaskForm):
    search = StringField('Search', validators=[DataRequired()])
    submit = SubmitField('Submit')

# Amazing, I hate writing this stuff
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# Define a decorator to check if the user is authenticated
# No idea how this works...  Magic.
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if users != None:
            if session.get("user") is None:
                return redirect(url_for('login'))
        return view(**kwargs)        
    return wrapped_view

# The default chat view
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():

    # The single input box and submit button
    form = SearchForm()

    if form.validate_on_submit():
        # Get the form variables
        form_result = request.form.to_dict(flat=True)
        # Send to search here
        posts = search_posts(form_result["search"])
    else:
        # Query mongo for blog posts
        posts = col.find().sort([("post_date", -1)]).limit(5)
    
    # Spit out the template
    return render_template('index.html', posts=posts, form=form)

# The default chat view
@app.route('/post', methods=['GET', 'POST'])
@app.route('/post/<id>', methods=['GET', 'POST'])
@login_required
def post(id=None):

    # The single input box and submit button
    form = BlogPostForm()
    form.style.data = DEFAULT_STYLE
    now = datetime.datetime.now()
    form.post_date.data = now.strftime("%Y-%m-%d")
    form.tags.data = DEFAULT_TAGS
    form.categories.data = DEFAULT_CATEGORY
    
    if form.validate_on_submit():
        # Get the form variables and remove the extra junk
        form_result = request.form.to_dict(flat=True)
        form_result.pop('csrf_token')
        form_result.pop('submit')

        # Create an embedding for the facts
        form_result["fact_embedding"] = embed(form_result["facts"])

        # AI Generate the post from the facts if post is blank, if it's not blank I'm assuming we're editing
        if form_result["post"] == "":
            subject = form_result["subject"]
            facts = form_result["facts"]
            style = form_result["style"]
            prompt = DEFAULT_PROMPT.format(facts=facts,subject=subject,style=style)
            form_result["post"] = llm_local(prompt, DEFAULT_SYSTEM, 0.7) + "\n * Human Intervention: None\n"

        # Store the post by replacing or inserting
        if id:
            col.replace_one({'_id': ObjectId(id)}, form_result)
        else:
            col.insert_one(form_result)

        return redirect(url_for('index'))
    else:
        if id:
            post = col.find_one({'_id': ObjectId(id)})
            form.subject.data = post["subject"]
            form.facts.data = post["facts"]
            form.style.data = post["style"]
            form.post_date.data = post["post_date"]
            if "tags" in post:
                form.tags.data = post["tags"]
            if "categories" in post:
                form.categories.data = post["categories"]
            form.post.data = post["post"]
        
    # Spit out the template
    return render_template('post.html', form=form)

# Generate the content for Hugo
@app.route('/generate')
@login_required
def generate():
    # Query mongo for blog posts
    posts = col.find()
    for post in posts:
        filename = site_path + post["subject"] + ".md"
        post_text = post["post"]
        facts = post["facts"]

        # Generate fact strings
        fact_string = ""
        for fact in facts.split("\n"):
            if fact != "":
                fact_string = fact_string + F"* {fact}\n"

        # Add the hugo header
        post_header = hugo_header.replace("{title}", post["subject"])
        post_header = post_header.replace("{date}", post["post_date"])
        post_header = post_header.replace("{tags}", str(post["tags"].split(",")))
        post_header = post_header.replace("{categories}", str(post["categories"].split(",")))
        post_text = post_header + post_text

        with open(filename, 'w', encoding='utf-8') as post_file:
            post_file.write(post_text + "\n### Facts Used:\n" + fact_string)

    return redirect(url_for('index'))


# This post is bad, nuke it from orbit
@app.route('/delete/<id>')
@login_required
def fact_delete(id):
    col.delete_one({'_id': ObjectId(id)})
    return redirect(url_for('index'))
    
# Login/logout routes that rely on the user being stored in session
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if form.username.data in users:
            if form.password.data == users[form.username.data]:
                session["user"] = form.username.data
                return redirect(url_for('index'))
    return render_template('login.html', form=form)

# We finally have a link for this now!
@app.route('/logout')
def logout():
    session["user"] = None
    return redirect(url_for('login'))