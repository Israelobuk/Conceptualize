from .slugs import slug


def product_url(label):
    return '/products/'+slug(label)
