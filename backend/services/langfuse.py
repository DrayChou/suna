import os
from langfuse import Langfuse

public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
secret_key = os.getenv("LANGFUSE_SECRET_KEY")
host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

langfuse = None
if public_key and secret_key:
    langfuse = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host
    )
else:
    # Create a dummy langfuse object for when credentials are not provided
    class DummyLangfuse:
        def trace(self, *args, **kwargs):
            return self
        def span(self, *args, **kwargs):
            return self
        def generation(self, *args, **kwargs):
            return self
        def update(self, *args, **kwargs):
            return self
        def end(self, *args, **kwargs):
            return self
        def __getattr__(self, name):
            return lambda *args, **kwargs: self
    
    langfuse = DummyLangfuse()
