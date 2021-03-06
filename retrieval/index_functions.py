# functions to add prebuilt BOWs to index
#
# Copyright:   (c) Daniel Duma 2014
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import print_function

from __future__ import absolute_import
import logging
from six import string_types
import json

import db.corpora as cp
import proc.doc_representation as doc_representation
from retrieval.elastic_writer import BufferedElasticWriter, ElasticWriter, ES_TYPE_DOC


def defaultAddDocument(writer, new_doc, metadata, fields_to_process, bow_info, append_fields=[]):
    """
        Add a document to the index.

        :param new_doc: dict of fields with values
        :type new_doc:dict
        :param metadata: ditto
        :type metadata:dict
        :param fields_to_process: only add these fields from the doc dict
        :type fields_to_process:list
    """

    if not isinstance(bow_info, string_types):
        bow_info = json.dumps(bow_info)

    body = {"guid": metadata["guid"],
            "metadata": metadata,
            "bow_info": bow_info,
            }

    data_to_append = ""
    for field in append_fields:
        data_to_append += new_doc[field] + " "

    for field in fields_to_process:
        data = new_doc[field]
        if field not in append_fields:
            data = data + " " + data_to_append
        body[field] = data

    writer.addDocument(body)


ADD_DOCUMENT_FUNCTION = defaultAddDocument


def docIsAlreadyInIndex(guid, index_name):
    """
        Returns True if document was already added to index
    """
    return cp.Corpus.es.exists(id=guid, index=index_name, doc_type=ES_TYPE_DOC)


def addBOWsToIndex(guid, indexNames, index_max_year, fwriters=None, full_corpus=True, force_add=False):
    """
        For one guid, add all its BOWs to the given index

        CHANGES: No longer builds the BOWs. If they're not there, they aren't

        :param guid: guid of the paper
        :param indexNames: a fully expanded dict of doc_methods
        :param index_max_year: the max year to accept to add a file to the index
    """
    meta = cp.Corpus.getMetadataByGUID(guid)
    if not meta:
        logging.error("Error: can't load metadata for paper %s" % guid)
        return

    if not fwriters:
        fwriters = {}
        for indexName in indexNames:
            actual_dir = cp.Corpus.getRetrievalIndexPath(None, indexName, full_corpus=full_corpus)
            fwriters[indexName] = ElasticWriter(actual_dir, cp.Corpus.es)

    for indexName in indexNames:
        if not force_add and docIsAlreadyInIndex(guid, indexName):
            continue

        index_data = indexNames[indexName]
        method = index_data["method"]
        parameter = index_data["parameter"]
        ilc_parameter = index_data.get("ilc_parameter", "")
        append_fields = index_data.get("append_fields", [])

        if index_data["type"] in ["standard_multi", "inlink_context"]:  # annotated_boost?
            if index_max_year:
                if int(meta["year"]) > int(index_max_year):
                    continue
            # addOrBuildBOWToIndex(fwriters[indexName], guid, index_data)
            bow_filename = cp.Corpus.cachedDataIDString("bow", guid, index_data)
            try:
                bows = cp.Corpus.loadCachedJson(bow_filename)
                addLoadedBOWsToIndex(fwriters[indexName], guid, bows, index_data, append_fields=append_fields)
            except:
                print("ERROR: Couldn't load BOW ", bow_filename)

        # elif index_data["type"] in ["inlink_context"]:
        #     addOrBuildBOWToIndexExcludingCurrent(fwriters[indexName], guid, cp.Corpus.TEST_FILES, index_max_year,
        #                                          method, parameter)
        elif index_data["type"] == "ilc_mashup":
            bows = doc_representation.mashupBOWinlinkMethods(guid, [guid], index_max_year, indexNames[indexName],
                                                             full_corpus=True)
            if not bows:
                print("ERROR: Couldn't load prebuilt BOWs for mashup with inlink_context and ", method, ", parameters:",
                      parameter, ilc_parameter)
                raise FileNotFoundError
                continue
            addLoadedBOWsToIndex(fwriters[indexName], guid, bows, index_data, append_fields=append_fields)


# def addOrBuildBOWToIndex(writer, guid, index_data, full_corpus=False, filter_options={},  append_fields=[]):
#     """
#         Loads JSON file with BOW data to doc in index, NOT filtering for anything
#     """
#     bow_filename = cp.Corpus.cachedDataIDString("bow", guid, index_data)
#     try:
#         bows = cp.Corpus.loadCachedJson(bow_filename)
#     except:
#         bows = None
#
#     if bows is None:
#         print("BOW not found, rebuilding")
#         bows = prebuildMulti(index_data["method"],
#                              index_data["parameters"],
#                              index_data["function_name"],
#                              None,
#                              None,
#                              guid,
#                              False,
#                              filter_options=filter_options
#                              )  # !TODO rhetorical_annotations here?
#         # Note: prebuildMulti will return a dict[param]=list of bows
#         bows = bows[index_data["parameter"]]
#
#     ##    if not isinstance(bows, list):
#     ##        print("BOWS IS NOT A LIST")
#     ##        print("guid:", guid)
#     ##        print("index_data:", index_data)
#     ##        print("Type:", type(bows))
#     assert isinstance(bows, list)
#     addLoadedBOWsToIndex(writer, guid, bows, index_data, append_fields=append_fields)


# def addOrBuildBOWToIndexExcludingCurrent(writer, guid, exclude_list, max_year, index_data, full_corpus=False, append_fields=[]):
#     """
#         Loads JSON file with BOW data to index, filtering for
#         inlink_context, excluding what bits
#         came from the current exclude_list, posterior year, same author, etc.
#     """
#     bow_filename = cp.Corpus.cachedDataIDString("bow", guid, index_data)
#     try:
#         bows = cp.Corpus.loadCachedJson(bow_filename)
#     except:
#         bows = None
#
#     if not bows:
#         bows = prebuildMulti(index_data["method"],
#                              index_data["parameters"],
#                              index_data["function_name"],
#                              doc=None,
#                              doctext=None,
#                              guid=guid,
#                              overwrite_existing_bows=False,
#                              filter_options={})  # !TODO rhetorical_annotations here?
#
#     assert isinstance(bows, list)
#
#     # joinTogetherContext?
#     bows = doc_representation.filterInlinkContext(bows, exclude_list, full_corpus=full_corpus,
#                                                   filter_options={"max_year": max_year})
#
#     assert isinstance(bows, list)
#     addLoadedBOWsToIndex(writer,
#                          guid,
#                          bows,
#                          {"method": index_data["method"],
#                           "parameter": index_data["parameter"]},
#                          append_fields=append_fields)


def addLoadedBOWsToIndex(writer, guid, bows, bow_info, append_fields=[]):
    """
        Adds loaded bows as pointer to a file [fn]/guid [guid]

        :param writer: writer instance
        :param guid: ditto
        :param bows: list of dicts, with one key per field to index [{"title":"","abstract":""},{},...]
        :param bow_info: a dict with info about the bow being added, e.g. method that generated it and parameter
    """
    i = 0
    # base_metadata = cp.Corpus.getMetadataByGUID(guid)
    # assert (base_metadata)

    assert isinstance(bows, list)
    for new_doc in bows:  # takes care of passage
        if len(new_doc) == 0:  # if the doc dict contains no fields
            continue

        fields_to_process = [field for field in new_doc if field not in doc_representation.FIELDS_TO_IGNORE]

        if len(fields_to_process) == 0:  # if there is no overlap in fields to add
            continue

        total_numTerms = 0

        # metadata = deepcopy(base_metadata)
        metadata = {"guid": guid}

        for field in ["_full_text", "_full_ilc", "inlink_context"]:
            if field in new_doc:
                field_len = len(new_doc[field].split())
                total_numTerms += field_len

        bow_info["passage_num"] = i
        bow_info["total_passages"] = len(bows)
        bow_info["total_numterms"] = total_numTerms

        ADD_DOCUMENT_FUNCTION(writer, new_doc, metadata, fields_to_process, bow_info, append_fields=append_fields)
        i += 1


def main():
    ##    cp.useElasticCorpus()
    ##    cp.Corpus.connectCorpus(r"g:\nlp\phd\pmc_coresc")
    ##    guids=["07eb18ef-2e86-4955-882d-c63e472e51c6", "d8a17083-53cc-43be-baa1-b6d6e85e711a"]
    ##    index_data={u'bow_name': u'az_annotated', u'parameters': [1], u'type': u'standard_multi', u'max_year': 2013, u'index_filename': u'az_annotated_pmc_2013_1', u'options': {}, u'index_field': u'1', u'parameter': 1, u'method': u'az_annotated', u'function_name': u'getDocBOWannotated'}
    ##    indexNames={u'az_annotated_pmc_2013_1': {u'bow_name': u'az_annotated', u'parameters':[1], u'type': u'standard_multi', u'max_year': 2013, u'index_filename': u'az_annotated_pmc_2013_1', u'options': {}, u'index_field': u'1', u'parameter': 1, u'method': u'az_annotated', u'function_name': u'getDocBOWannotated'}}
    ##    for guid in guids:
    ##        addBOWsToIndex(guid, indexNames, 2013)
    pass


if __name__ == '__main__':
    main()
