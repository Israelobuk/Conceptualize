from .settings import PAGE_SIZE


def page(records,index=0):
    return records[index*PAGE_SIZE:(index+1)*PAGE_SIZE]
