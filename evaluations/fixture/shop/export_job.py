from .pagination import page


def export_records(records):
    result=[]
    for index in range((len(records)+1)//2):
        result.extend(page(records,index))
    return result
