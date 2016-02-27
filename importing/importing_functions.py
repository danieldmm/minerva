# <purpose>
#
# Copyright:   (c) Daniel Duma 2015
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

import logging
from copy import deepcopy

from minerva.proc.general_utils import (normalizeTitle, ensureDirExists)

import minerva.db.corpora as cp
from minerva.scidoc.xmlformats.read_auto import AutoXMLReader

def addSciDocToDB(doc, import_id, collection_id):
    """
        Extends metadata from doc and adds to database
    """
    meta=deepcopy(doc["metadata"])

    if meta.get("corpus_id","")=="":
        meta["corpus_id"]=meta["pm_id"] if meta.has_key("pm_id") else ""

    meta["norm_title"]=normalizeTitle(meta["title"])
    meta["numref"]=str(len(doc["references"]))
    meta["outlinks"]=[]
    meta["inlinks"]=[]
    meta["num_citations"]=len(doc["citations"])

    # this is for later processing and adding to database
    meta["num_in_collection_references"]=0
    meta["num_references"]=len(doc["references"])
    meta["num_resolvable_citations"]=0
    meta["num_citations"]=0
    meta["import_id"]=import_id
    meta["collection_id"]=collection_id
    cp.Corpus.addPaper(meta)

def convertXMLAndAddToCorpus(file_path, corpus_id, import_id, collection_id, xml_string=None):
    """
        Reads the input XML and saves a SciDoc
    """
    if cp.Corpus.getMetadataByField("metadata.corpus_id", corpus_id):
        print("Document %s is already in the collection" % corpus_id)
        # Doc is already in collection
        return

    reader=AutoXMLReader()
##    try:
    if xml_string:
        doc=reader.read(xml_string, file_path)
    else:
        doc=reader.readFile(file_path)
##    except:
##        logging.exception("Could not read file.")
##        return

    doc.metadata["norm_title"]=normalizeTitle(doc.metadata["title"])
    if doc.metadata.get("guid", "") == "":
        doc.metadata["guid"]=cp.Corpus.generateGUID(doc.metadata)
    if doc.metadata.get("corpus_id", "") == "":
        doc.metadata["corpus_id"]=corpus_id
    cp.Corpus.saveSciDoc(doc)
    addSciDocToDB(doc, import_id, collection_id)
    return doc

def updatePaperInCollectionReferences(doc_id, import_options):
    """
        Updates a single paper's in-collection references
    """
    assert doc_id != ""
    doc_meta=cp.Corpus.getMetadataByGUID(doc_id)
##        print "Processing in-collection references for ", doc_meta["filename"]

    doc_file=cp.Corpus.loadSciDoc(doc_id)
    if not doc_file:
        print("Cannot load",doc_meta["filename"])
        return None

    citations_data=cp.Corpus.loadOrGenerateResolvableCitations(doc_file)

    resolvable=citations_data["resolvable"]
    in_collection_references=citations_data["outlinks"]
    missing_references=citations_data.get("missing_references",[])
    doc_meta["num_in_collection_references"]=len(in_collection_references)
    doc_meta["num_references"]=len(doc_file["references"])
    doc_meta["num_resolvable_citations"]=len(resolvable)
    doc_meta["num_citations"]=len(doc_file["citations"])

    for ref in in_collection_references:
        match_meta=cp.Corpus.getMetadataByGUID(ref)
        if match_meta:
            if match_meta["guid"] not in doc_meta["outlinks"]:
                doc_meta["outlinks"].append(match_meta["guid"])
            if doc_meta["guid"] not in match_meta["inlinks"]:
                match_meta["inlinks"].append(doc_meta["guid"])
                cp.Corpus.updatePaper(match_meta)
        else:
            logging.warning("Bizarre: record for GUID %s is missing after matching first" % ref)
            pass

##    assert len(resolvable) == 0

    cp.Corpus.updatePaper(doc_meta)
    if import_options.get("list_missing_references", False):
        for ref in missing_references:
            cp.Corpus.addMissingPaper(copyDictExceptKeys(ref,["xml"]))
    return doc_meta


def main():
    pass

if __name__ == '__main__':
    main()