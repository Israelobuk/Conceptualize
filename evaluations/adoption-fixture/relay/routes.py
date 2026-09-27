from .labels import label
def route(text):
    return "/messages/" + label(text)
