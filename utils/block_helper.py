
from typing import List, Union
import uuid, copy, boto3

textract_client = boto3.client("textract")

class DictionaryClass:
    """Class to define an object as a dictionary."""

    def __str__(self):
        """Return a string representation of the object as a dictionary."""
        return str(self.__dict__)

    def __repr__(self):
        """Return a string representation of the object."""
        return str(self)

    def reprJSON(self):
        """Return dictionary representation of the object."""
        return self.__dict__


class BoundingBox(DictionaryClass):
    """Class to define a Semi-Structured BoundingBox object."""

    def __init__(self, width: int, height: int, left: int, top: int):
        self.Width = width
        self.Top = top
        self.Left = left
        self.Height = height

    def extend_bounding_box(self, bounding_box: 'BoundingBox'):
        """Extend the BoundingBox object's dimensions to another BoundingBox object."""
        selfRight = self.Left + self.Width
        selfBottom = self.Top + self.Height
        bbRight = bounding_box.Left + bounding_box.Width
        bbBottom = bounding_box.Top + bounding_box.Height
        self.Width = abs(min(self.Left, bounding_box.Left) - max(selfRight, bbRight))
        self.Height = abs(min(self.Top, bounding_box.Top) - max(selfBottom, bbBottom))
        if self.Left > bounding_box.Left:
            self.Left = bounding_box.Left
        if self.Top > bounding_box.Top:
            self.Top = bounding_box.Top


class Point(DictionaryClass):
    """Class to define a Semi-Structured Point object."""

    def __init__(self, x: int, y: int):
        self.X = x
        self.Y = y


class Geometry(DictionaryClass):
    """Class to define an Semi-Structured Block object."""

    def __init__(self, width: int, height: int, left: int, top: int):
        self.BoundingBox = BoundingBox(width, height, left, top)
        self.Polygon = get_points(width, height, left, top)

    def extend_geometry(self, geometry: 'Geometry'):
        """Extend the Geometry object's BoundingBox to another Geometry object."""
        self.BoundingBox.extend_bounding_box(geometry.BoundingBox)
        self.Polygon = extend_polygon(self.Polygon, geometry.Polygon)


class Relationship(DictionaryClass):
    """Class to define an Semi-Structured Relationship object."""

    def __init__(self, ids: List[str], type: str):
        self.Ids = ids if ids else []
        self.Type = type


class Block(DictionaryClass):
    """Class to define an Semi-Structured Block object."""

    def __init__(self, page: int, block_type: str, text: str, index: int, geometry: Union[Geometry, None] = None, parent_block_index=-1):
        self.BlockType = block_type
        self.Id = str(uuid.uuid4())
        self.Text = text
        self.Geometry = geometry
        self.Relationships: List[Relationship] = []
        self.Page = page

        self.parentBlockIndex = parent_block_index
        self.blockIndex = index

    def extend_geometry(self, geometry: Geometry):
        """Extend the Block object's Geometry to another Geometry object."""
        if not self.Geometry:
            self.Geometry = copy.deepcopy(geometry)
        else:
            self.Geometry.extend_geometry(geometry)


def get_points(width: int, height: int, left: int, top: int):
    """Return a list of Point objects from a boundary."""
    return [Point(left, top), Point(left + width, top), Point(left + width, top + height), Point(left, top + height)]


def extend_polygon(polygon1: List[Point], polygon2: List[Point]):
    """Return a polygon extended from another polygon."""
    bounding_box_1 = BoundingBox(polygon1[2].X - polygon1[0].X, polygon1[2].Y - polygon1[0].Y, polygon1[0].X, polygon1[0].Y)
    bounding_box_2 = BoundingBox(polygon2[2].X - polygon2[0].X, polygon2[2].Y - polygon2[0].Y, polygon2[0].X, polygon2[0].Y)
    bounding_box_1.extend_bounding_box(bounding_box_2)

    return get_points(bounding_box_1.Width, bounding_box_1.Height, bounding_box_1.Left, bounding_box_1.Top)


def textract_block_to_block_relationship(textract_relationship_list: List[dict]):
    """Return a block relationship object from a Textract block object."""
    ids = []
    if textract_relationship_list:
        for relationship in textract_relationship_list:
            if relationship['Type'] != 'CHILD':
                continue
            ids.extend(relationship['Ids'])
            break
    return Relationship(ids, 'CHILD')


def textract_block_to_block(page: int, textract_block: dict, index: int, parent_index: int = -1):
    """Return a block object from a Textract block object."""
    textract_block_bounding_box = textract_block['Geometry']['BoundingBox']
    block = Block(
        page, 
        textract_block['BlockType'], 
        textract_block['Text'], 
        index,
        Geometry(
            textract_block_bounding_box['Width'], 
            textract_block_bounding_box['Height'],
            textract_block_bounding_box['Left'], 
            textract_block_bounding_box['Top']
        )
    )
    block.Id = textract_block['Id']
    block.Relationships = [] if 'Relationships' not in textract_block else [textract_block_to_block_relationship(textract_block['Relationships'])]
    block.parentBlockIndex = parent_index
    return block


def blocks_from_scanned_pdf(bucket, key, page_number=1):
    """Return a list of blocks from a scanned PDF."""
    result = textract_client.detect_document_text(
        Document={
            'S3Object': {
                'Bucket': bucket,
                'Name': key,
            }
        }
    )
    textract_blocks = result["Blocks"]
    textract_line_blocks = [block for block in textract_blocks if block['BlockType'] == 'LINE']
    textract_word_blocks = [block for block in textract_blocks if block['BlockType'] == 'WORD']

    # use to quickly retrieve word blocks
    idToWordBlock = {b['Id']: b for b in textract_blocks if b['BlockType'] == 'WORD'}

    blocks = []
    # for each textract line block, create a line block, then create the word blocks by looping through its Relationships,
    #   if the relationship is of type CHILD, loop through the relationships Ids array and create word blocks
    index = -1
    for textract_lb in textract_line_blocks:
        index += 1
        line_block = textract_block_to_block(page_number, textract_lb, index)
        line_index = index

        blocks.append(line_block)
        if line_block.Relationships:
            for id in line_block.Relationships[0].Ids:
                index += 1
                textract_word_block = idToWordBlock[id]
                word_block = textract_block_to_block(page_number, textract_word_block, index, line_index)
                blocks.append(word_block)

    line_blocks = [block for block in blocks if block.BlockType == 'LINE']
    word_blocks = [block for block in blocks if block.BlockType == 'WORD']

    return blocks


# def JSONHandler(Obj):
#     """Return a JSON representation from an object."""
#     if hasattr(Obj, 'reprJSON'):
#         return Obj.reprJSON()
#     else:
#         raise TypeError('Object of type %s with value of %s is not JSON serializable' % (type(Obj), repr(Obj)))


def JSONHandler(Obj):
    """Return a JSON representation from an object."""
    if isinstance(Obj, list):
        for i, item in enumerate(Obj):
            Obj[i] = JSONHandler(item)
    if hasattr(Obj, 'reprJSON'):
        Obj = Obj.reprJSON()
        for key in Obj.keys():
            value = Obj[key]
            Obj[key] = JSONHandler(value)
    return Obj