"""Local-prototype privacy controls. These are not a hosted authentication system."""
import base64
import html
import os
from functools import wraps
from pathlib import Path
from langsmith import tracing_context

LOOPBACK={'127.0.0.1','localhost','::1'}


def local_only(address):
    if address not in LOOPBACK:
        raise ValueError('This private-data prototype only runs on localhost. Start from week2 with --server.address 127.0.0.1. Public sharing requires proper login and private media storage first.')


def private_directory(path):
    path=Path(path)
    if path.is_symlink():raise ValueError('Private storage directories must not be symbolic links.')
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=='posix':path.chmod(0o700)
    return path


def private_file(path,content=None):
    path=Path(path)
    if path.is_symlink():raise ValueError('Private storage files must not be symbolic links.')
    if content is not None:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(content)
    elif not path.exists():
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    if os.name=='posix':path.chmod(0o600)


def private_tracing(function):
    """Override inherited tracing settings before inputs enter LangGraph/LangSmith."""
    @wraps(function)
    def wrapper(*args,**kwargs):
        with tracing_context(enabled=False):return function(*args,**kwargs)
    return wrapper


def inline_photo(content,alt):
    # Only re-encoded JPEG bytes from Store are passed here. No globally shared media URL.
    encoded=base64.b64encode(content).decode('ascii')
    return f'<img src="data:image/jpeg;base64,{encoded}" alt="{html.escape(alt,quote=True)}" style="width:100%;border-radius:14px" />'

