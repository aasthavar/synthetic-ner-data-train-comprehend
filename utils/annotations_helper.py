import re
from .entities import global_entities

def get_word_id(word, blocks):
    block_id = None
    for block in blocks:
        if block["BlockType"] == "WORD" and (word in block["Text"]): # TODO: Extend to incorporate multiple occurrences of same word
            return block["Id"]
    return block_id

def get_line_id_text(word_id, blocks):
    line_id = None
    text = None
    for block in blocks:
        if block["BlockType"] == "LINE":
            for relationship in block["Relationships"]:
                if word_id in relationship["Ids"]: # word belongs to this line
                    line_id = block["Id"]
                    text = block["Text"]
                    return line_id, text
    return line_id, text

def get_entities(df, blocks):
    entities = []
    for idx, row in df.iterrows():
        block_references = []
        lines_words_dict = {}
        words = str(row['value']).split(' ')
        for word in words:
            word_id = get_word_id(word, blocks)
            if word_id != None:
                # print(f"word={word}, word_id={word_id}") 
                # we have word_id, use this to find to which line it belongs to
                line_id, line_text = get_line_id_text(word_id, blocks)
                if line_id not in lines_words_dict.keys():
                    lines_words_dict[line_id] = []
                bo, eo = re.search(word, line_text).span()
                lines_words_dict[line_id].append({
                    "BeginOffset": bo,
                    "EndOffset": eo,
                    "ChildBlockId": word_id
                })
            else:
                print(f"word={word} not found!")
        
        for line_id, child_blocks in lines_words_dict.items():
            min_bo = min([item["BeginOffset"] for item in child_blocks])
            max_eo = max([item["EndOffset"] for item in child_blocks])
            for i, child in enumerate(child_blocks):
                bo, eo = child['BeginOffset'], child['EndOffset']
                child['BeginOffset'] = 0
                child['EndOffset'] = eo-bo 
                child_blocks[i] = child
            block_references.append({
                "BlockId": line_id,
                "ChildBlocks": child_blocks,
                "BeginOffset": min_bo,
                "EndOffset": max_eo
            })    
        entity = {
            "BlockReferences": block_references, # list of block_reference elements
            "Text": row['value'],
            "Type": row['type'],
            "Score": 1
        }
        entities.append(entity)
        global_entities[row['type']] += 1
    return entities

def clean_entities(entities):
    entities_clean = []
    for entity in entities:
        if len(entity['BlockReferences']) > 0: # not empty:
            entities_clean.append(entity)
    return entities_clean

def get_annotations(df, blocks, s3_blocks_path, ann_file_key):
    entities = get_entities(df, blocks)
    entities_clean = clean_entities(entities)
    annotations = {
        "Blocks": blocks,
        "BlocksS3Ref": s3_blocks_path,
        "DocumentMetadata": {
            "Pages": "1",
            "PageNumber": "1",
        },
        "Version": "2021-04-30",
        # "DocumentType": "ScannedPDF",
        "DocumentType": "NativePDF", # TODO: Change it to ScannedPDF and test again
        "Entities": entities_clean, # list of entity elements
        "File": ann_file_key  
    }
    return annotations

def clean_blocks(blocks):
    for b in blocks:
        if 'parentBlockIndex' in b:
            del b['parentBlockIndex']
        if 'blockIndex' in b:
            del b['blockIndex']
    return blocks