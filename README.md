# FactWeave

Facts are all you need (tm) ... and maybe an LLM, a text embedder, Atlas Mongo and some python!

A CMS for producing a static blog site using Hugo and AI. Stop writing long blog posts yourself and your locally hosted open source LLM to do it.

* Create subjects and facts, and have the LLM convert them into blog posts.  
* Export the articles to a static site for upload to your hosting platform.

![FactWeave UI Screenshot](images/ui.png)
![Factweave New Post](images/newpost.png)

Example Site:  https://ai.dungeons.ca

## FactWeave Installation

```
pip install -r requirements.txt
```

Rename the mode.json.sample to model.json.  This file is used to set the prompt format and ban tokens, the default is ChatML format so it should work with most recent models.  Set the llama_endpoint to point to your llama.cpp running in server mode.

Also rename the embedder.json.sample to embedder.json.  This will be the endpoint URL for your text embedder service.  I highly recommend using https://github.com/patw/InstructorVec  It's easy to operate and will work out of the box for this application.

Finally rename sample.env to .env and fill in your Atlas connection string and Hugo content/posts path!

### Semantic Search

If you want to enable search, write a blog post first and then add the following search index to your Atlas Search.  This won't work if the ```posts``` collections haven't been created by the app yet.

```
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "fact_embedding": [
        {
          "type": "knnVector",
          "dimensions": 768,
          "similarity": "cosine"
        }
      ]
    }
  }
}
```

### Setting up the Text Embedder

I built this app using https://github.com/patw/InstructorVec however you could modify the source to use Mistral.ai or OpenAI embedding.  Be sure to modify the vector search indexes to use the proper number of dimensions.  

### Downloading an LLM model

Follow the instructions for llama.cpp or ollama for downloading and running models in server mode.

## Hugo Configuration

* Download and install Hugo from https://gohugo.io/ 
* Create a site using hugo new <site>
* Edit your hugo.toml to have a proper theme and site name
* Edit your content/about.md to have an about page
* Make note of your content/posts directory so you can configure your .env file to point to it (CONTENT variable)
* Build some automation to get hugo to regen the site and upload to your hosting platform!