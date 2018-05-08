# ElasticCorpus. Uses an ElasticSearch endpoint as the database of papers
#
# Copyright:   (c) Daniel Duma 2015
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import print_function

from __future__ import absolute_import
import sys, json, datetime, re, copy

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionTimeout, ConnectionError, TransportError
import requests
import six.moves.urllib.request, six.moves.urllib.parse, six.moves.urllib.error

from proc.general_utils import ensureTrailingBackslash
from scidoc.scidoc import SciDoc
from .base_corpus import BaseCorpus, TABLE_PAPERS, TABLE_CACHE, TABLE_AUTHORS, TABLE_LINKS, TABLE_MISSING_REFERENCES, \
    TABLE_SCIDOCS, TABLE_VENUES

ES_INDEX_PAPERS = "papers"
ES_INDEX_SCIDOCS = "scidocs"
ES_INDEX_CACHE = "cache"
ES_INDEX_AUTHORS = "authors"
ES_INDEX_LINKS = "links"
ES_INDEX_VENUES = "venues"
ES_INDEX_MISSING_REFERENCES = "missing_references"

ES_TYPE_PAPER = "paper"
ES_TYPE_SCIDOC = "scidoc"
ES_TYPE_CACHE = "cache"
ES_TYPE_AUTHOR = "author"
ES_TYPE_LINK = "link"
ES_TYPE_VENUE = "venue"
ES_TYPE_MISSING_REFERENCES = "missing_reference"

index_equivalence = {
    TABLE_PAPERS: {"index": ES_INDEX_PAPERS, "type": ES_TYPE_PAPER, "source": "metadata",
                   "non_nested_fields": ["norm_title", "author_ids", "has_scidoc"]},
    TABLE_SCIDOCS: {"index": ES_INDEX_SCIDOCS, "type": ES_TYPE_SCIDOC, "source": "scidoc"},
    TABLE_AUTHORS: {"index": ES_INDEX_AUTHORS, "type": ES_TYPE_AUTHOR, "source": "author"},
    TABLE_CACHE: {"index": ES_INDEX_CACHE, "type": ES_TYPE_CACHE, "source": "data"},
    TABLE_LINKS: {"index": ES_INDEX_LINKS, "type": ES_TYPE_LINK, "source": "link"},
    TABLE_VENUES: {"index": ES_INDEX_VENUES, "type": ES_TYPE_VENUE, "source": "venue"},
    TABLE_MISSING_REFERENCES: {"index": ES_INDEX_MISSING_REFERENCES, "type": ES_TYPE_MISSING_REFERENCES,
                               "source": "missing_reference"},
}

ES_ALL_INDECES = [ES_INDEX_PAPERS, ES_INDEX_SCIDOCS, ES_INDEX_CACHE,
                  ES_INDEX_LINKS, ES_INDEX_AUTHORS]


class ElasticCorpus(BaseCorpus):
    """
        ElasticSearch connection corpus
    """

    def __init__(self):
        """
            Basic creator
        """
        super(self.__class__, self).__init__()
        self.es = None

        self.query_filter = ""
        self.endpoint = None
        self.ALL_FILES = []
        self.TEST_FILES = []
        self.FILES_TO_IGNORE = []
        self.metadata_index = None
        self.paths.fullLuceneIndex = "index_"
        self.max_results = sys.maxsize

    def connectCorpus(self, base_directory, endpoint={"host": "localhost", "port": 9200}, initializing_corpus=False,
                      suppress_error=False):
        """
            If DB has been created, connect to it. Icf not, initialize it first.

            Args:
                base_directory: root dir of this corpus
                initializing_corpus: if True, create DB and directories
                suppress_error: if true, db doesn't complain if it's connected already
        """
        self.endpoint = endpoint
        self.setPaths(ensureTrailingBackslash(base_directory))

        if initializing_corpus:
            self.createAndInitializeDatabase()
        self.connectToDB(suppress_error)

    def createAndInitializeDatabase(self):
        """
            Ensures that the directory structure is in place and creates
            the SQLite database and tables
        """

        def createTable(name, settings, properties):
            """
            """
            if not self.es.indices.exists(index=index_equivalence[name]["index"]):
                self.es.indices.create(
                    index=index_equivalence[name]["index"],
                    body={"settings": settings,
                          "mappings": {index_equivalence[name]["type"]: {"properties": properties}}})

        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0
        }
        properties = {
            "guid": {"type": "string", "index": "not_analyzed"},
            "metadata": {"type": "nested"},
            "norm_title": {"type": "string", "index": "not_analyzed"},
            "author_ids": {"type": "string", "index": "not_analyzed", "store": True},
            "num_in_collection_references": {"type": "integer"},
            "num_resolvable_citations": {"type": "integer"},
            "num_inlinks": {"type": "integer"},
            "collection_id": {"type": "string", "index": "not_analyzed", "store": True},
            "import_id": {"type": "string", "index": "not_analyzed", "store": True},
            "time_created": {"type": "date"},
            "time_modified": {"type": "date"},
            "has_scidoc": {"type": "boolean", "index": "not_analyzed", "store": True},
            "flags": {"type": "string", "index": "not_analyzed", "store": True},
            # This is all now accessed through the nested metadata
            ##            "filename": {"type":"string", "index":"not_analyzed", "store":True},
            ##            "corpus_id": {"type":"string", "index":"not_analyzed"},
            ##            "title": {"type":"string", "store":True},##            "surnames": {"type":"string"},
            ##            "year": {"type":"integer"},
            ##            "in_collection_references": {"type":"string", "index":"not_analyzed", "store":True},
            ##            "inlinks": {"type":"string", "index":"not_analyzed", "store":True},
        }
        createTable("papers", settings, properties)

        properties = {
            "scidoc": {"type": "string", "index": "no", "store": True},
            "guid": {"type": "string", "index": "not_analyzed", "store": True},
            "time_created": {"type": "date"},
            "time_modified": {"type": "date"},
        }
        createTable("scidocs", settings, properties)

        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 1
        }
        properties = {
            "data": {"type": "string", "index": "no", "store": True},
            "time_created": {"type": "date"},
            "time_modified": {"type": "date"},
        }
        createTable("cache", settings, properties)

        properties = {
            "link": {"type": "nested"},
            ##                "guid_from": {"type":"string", "index":"not_analyzed", "store":True},
            ##                "guid_to": {"type":"string", "index":"not_analyzed", "store":True},
            ##                "authors_from": {"type":"string", "index":"not_analyzed", "store":True},
            ##                "authors_to": {"type":"string", "index":"not_analyzed", "store":True},
            ##                "self_citation": {"type":"boolean", "index":"not_analyzed", "store":True},
            ##                "year_from": {"type":"integer", "index":"not_analyzed", "store":True},
            ##                "year_to": {"type":"integer", "index":"not_analyzed", "store":True},
            ##                "numcitations": {"type":"integer", "index":"not_analyzed", "store":True},
            "time_created": {"type": "date"}}

        createTable("links", settings, properties)

        properties = {
            ##                "author_id": {"type":"string", "index":"not_analyzed", "store":True},
            "author": {"type": "nested"},
            ##                "given": {"type":"string", "index":"analyzed", "store":True},
            ##                "middle": {"type":"string", "index":"analyzed", "store":True},
            ##                "family": {"type":"string", "index":"analyzed", "store":True},
            ##                "papers": {"type":"string", "index":"not_analyzed", "store":True},
            ##                "papers_first_author": {"type":"string", "index":"not_analyzed", "store":True},
            ##                "papers_last_author": {"type":"string", "index":"not_analyzed", "store":True},
            ##                "affiliations": {"type":"nested", "index":"not_analyzed", "store":True},
            "time_created": {"type": "date"}
        }
        createTable("authors", settings, properties)

        properties = {
            "venue": {"type": "nested"},
            "time_created": {"type": "date"},
            "norm_title": {"type": "string", "index": "not_analyzed"},
        }
        createTable("venues", settings, properties)

        properties = {
            "missing": {"type": "nested"},
            "time_created": {"type": "date"},
            "norm_title": {"type": "string", "index": "not_analyzed"},
        }
        createTable("missing_references", settings, properties)

    def connectedToDB(self):
        """
            returns True if connected to DB, False otherwise
        """
        return self.es is not None

    def getRetrievalIndexPath(self, guid, index_filename, full_corpus=False):
        """
            Returns the path to the Lucene index for a test file in
            the corpus

            if full_corpus is True, this is the general index for that method
                else
            when using Citation Resolution (resolving only from the
            references at the bottom of a paper) it is the specific index for
            that file guid
        """
        if full_corpus:
            return "idx_" + index_filename
        ##            return index_filename
        else:
            guid = guid.lower()
            return "idx_" + guid + "_" + index_filename

    def getRecord(self, rec_id, table=TABLE_PAPERS, source=None):
        """
            Abstracts over getting data from a row in the db. Returns all the
            fields of the record for one type of table, or those specified in source.

            :param rec_id: id of the record
            :param table: table alias, e.g. [TABLE_PAPERS, TABLE_SCIDOCS]
            :param source: fields to return
        """
        self.checkConnectedToDB()

        if table not in index_equivalence:
            raise ValueError("Unknown record type")

        try:
            res = self.es.get(
                index=index_equivalence[table]["index"],
                doc_type=index_equivalence[table]["type"],
                id=rec_id,
                _source=source
            )
        except:
            raise ValueError("Not found: %s in index %s" % (rec_id, index_equivalence[table]["index"]))

        if not res:
            raise IndexError("Can't find record with id %s" % rec_id)
        return res["_source"]

    def setRecord(self, rec_id, body, table=TABLE_PAPERS, op_type="update"):
        """
            Abstracts over setting getting data for a row in the db.

            :param rec_id: id of the record
            :param table: table alias, e.g. ["papers", "scidocs"]
            :param body: data to set
        """
        self.checkConnectedToDB()

        if table not in index_equivalence:
            raise ValueError("Unknown record type")

        ##~        try:
        if op_type == "update":
            body = {"doc": body}
            self.es.update(
                index=index_equivalence[table]["index"],
                doc_type=index_equivalence[table]["type"],
                id=rec_id,
                body=body
            )
        elif op_type in ["index", "create"]:
            self.es.index(
                index=index_equivalence[table]["index"],
                doc_type=index_equivalence[table]["type"],
                op_type=op_type,
                id=rec_id,
                body=body
            )
        else:
            raise ValueError("Unkown op_type %s" % op_type)
        ##        except:
        ##            raise ValueError("Error writing record: %s in index %s : %s" % (rec_id,index_equivalence[table]["index"], str(sys.exc_info[:2])))

        return

    def getRecordField(self, rec_id, table=TABLE_PAPERS):
        """
            Abstracts over getting data from a row in the db. Returns one field
            for one type of table.

            All other "getter" functions like getMetadataByGUID and loadSciDoc
            are aliases for this function
        """
        return self.getRecord(rec_id, table, source=index_equivalence[table]["source"])[
            index_equivalence[table]["source"]]

    def recordExists(self, rec_id, table=TABLE_PAPERS):
        """
            Returns True if the specified record exists in the given table, False
            otherwise.
        """
        self.checkConnectedToDB()

        return self.es.exists(
            id=rec_id,
            index=index_equivalence[table]["index"],
            doc_type=index_equivalence[table]["type"],
        )

    def SQLQuery(self, query):
        """
            Runs a SQL Query, returning a dict per result with the fields required.

            :param query: SQL query
            :type query: string
        """
        url_query = six.moves.urllib.parse.quote(query.encode('utf8'))
        uri = "http://%s:%s/_sql/_explain?sql=%s" % (self.endpoint["host"], self.endpoint["port"], url_query)
        response = requests.get(uri)
        dsl_query = json.loads(response.text)

        if "error" in dsl_query:
            raise ConnectionError("Error in query: " + str(dsl_query["error"]["root_cause"]))

        dsl_query["body"] = {"query": dsl_query.pop("query")}
        dsl_query["from_"] = dsl_query.pop("from")
        dsl_query["_source_include"] = dsl_query["_source"]["includes"]
        dsl_query["_source_exclude"] = dsl_query["_source"]["excludes"]
        dsl_query.pop("_source")

        match = re.search(r"select.+?from[\s\"\']+([\w,]+)", query, flags=re.IGNORECASE)
        if match:
            table_name = match.group(1)
        else:
            table_name = "papers"

        dsl_query["index"] = index_equivalence[table_name]["index"]
        dsl_query["doc_type"] = index_equivalence[table_name]["type"]

        tmp_max = self.max_results
        ##        self.max_results=dsl_query["size"]
        if "size" in dsl_query:
            del dsl_query["size"]
        results = self.unlimitedQuery(**dsl_query)
        self.max_results = tmp_max

        results = [r["_source"] for r in results]
        if len(dsl_query["_source_include"]) == 1:
            results = [r[dsl_query["_source_include"][0]] for r in results]

        return results

    def cachedJsonExists(self, cache_type, guid, params=None):
        """
            True if the cached JSON associated with the given parameters exists
        """
        self.checkConnectedToDB()

        return self.es.exists(
            index=ES_INDEX_CACHE,
            doc_type=ES_TYPE_CACHE,
            id=self.cachedDataIDString(cache_type, guid, params)
        )

    def saveCachedJson(self, path, data):
        """
            Save anything as JSON

            :param path: unique ID of resource to load
            :param data: json-formatted string or any data
        """
        self.checkConnectedToDB()

        timestamp = datetime.datetime.now()
        self.es.index(
            index=ES_INDEX_CACHE,
            doc_type=ES_TYPE_CACHE,
            id=path,
            op_type="index",
            body={
                "data": json.dumps(data),
                "time_created": timestamp,
                "time_modified": timestamp,
            }
        )

    def loadCachedJson(self, path):
        """
            Load precomputed JSON

            :param path: unique ID of resource to load
        """
        return json.loads(self.getRecordField(path, TABLE_CACHE))

    def loadSciDoc(self, guid, ignore_errors=None):
        """
            If a SciDocJSON file exists for guid, it returns it, otherwise None
        """
        data = json.loads(self.getRecordField(guid, TABLE_SCIDOCS))
        return SciDoc(data, ignore_errors=ignore_errors)

    def saveSciDoc(self, doc):
        """
            Saves the document as JSON in the index
        """
        self.checkConnectedToDB()

        attempts = 0
        while attempts < 3:
            try:
                timestamp = datetime.datetime.now()
                self.es.index(
                    index=ES_INDEX_SCIDOCS,
                    doc_type=ES_TYPE_SCIDOC,
                    id=doc["metadata"]["guid"],
                    op_type="index",
                    body={
                        "scidoc": json.dumps(doc.data),
                        "guid": doc["metadata"]["guid"],
                        "time_created": timestamp,
                        "time_modified": timestamp,
                    }
                )
                break
            except ConnectionTimeout:
                attempts += 1

    def connectToDB(self, suppress_error=False):
        """
            Connects to database
        """
        self.es = Elasticsearch([self.endpoint], timeout=60)
        self.es.retry_on_timeout = True

    def getMetadataByGUID(self, guid):
        """
            Returns a paper's metadata by GUID
        """
        return self.getRecordField(guid, "papers")

    def getMetadataByField(self, field, value):
        """
            Returns a paper's metadata by any other field
        """
        self.checkConnectedToDB()

        query = self.filterQuery("%s:\"%s\"" % (field, value))

        res = self.es.search(
            index=ES_INDEX_PAPERS,
            doc_type=ES_TYPE_PAPER,
            _source="metadata",
            size=1,
            q=query)

        hits = res["hits"]["hits"]
        if len(hits) == 0:
            return None

        return hits[0]["_source"]["metadata"]

    def setMetadata(self, metadata, op_type="update"):
        """
        Updates the metadata for one paper

        """
        meta = self.getFullPaperData("guid", metadata["guid"])
        meta["metadata"] = metadata
        self.setRecord(meta["guid"], meta, op_type=op_type)

    def getFullPaperData(self, field, value):
        """
            Returns a paper's metadata
        """
        self.checkConnectedToDB()

        query = self.filterQuery("%s:\"%s\"" % (field, value))

        res = self.es.search(
            index=ES_INDEX_PAPERS,
            doc_type=ES_TYPE_PAPER,
            size=1,
            q=query)

        hits = res["hits"]["hits"]
        if len(hits) == 0:
            return None

        return hits[0]["_source"]

    def getStatistics(self, guid):
        """
            Easy method to get a paper's statistics
        """
        return self.getRecord(guid, "papers", "statistics")["statistics"]

    def setStatistics(self, guid, stats):
        """
            Easy method to set a paper's statistics
        """
        return self.setRecord(guid, {"statistics": stats}, "papers", op_type="update")

    def filterQuery(self, query, table=TABLE_PAPERS):
        """
            Adds a global filter to the query so it only matches the selected
            collection, date, etc.

            :param table: only works for TABLE_PAPERS
            :param query: string
        """
        if table != "papers":
            raise NotImplementedError

        if self.query_filter != "":
            return self.query_filter + " (" + query + ")"
        else:
            return query

    def listFieldByField(self, field1, field2, value, table=TABLE_PAPERS, max_results=100):
        """
            Returns a list: for each paper, field1 if field2==value
        """
        self.checkConnectedToDB()

        if table not in index_equivalence:
            raise ValueError("Unknown record type")

        query = self.filterQuery("%s:\"%s\"" % (field2, value))

        hits = self.unlimitedQuery(
            q=query,
            index=index_equivalence[table]["index"],
            doc_type=index_equivalence[table]["type"],
            _source=field1,

        )

        return [r["_source"][field1] for r in hits]

    def isNestedQuery(self, query_string):
        """
            Returns True if a nested field is found in the query string, e.g.
            author.name

            :param query_string: query string
            :returns: boolean
        """
        query_without_quotes = re.sub(r"[^\\]\".*?[^\\]\"", "", query_string)
        nested_query = re.search(r"[a-zA-Z]\.[a-zA-Z]", query_without_quotes) is not None
        return nested_query

    def abstractNestedResults(self, query_string, hits, field=None):
        """
            Selects results from elasticsearch API
        """
        if self.isNestedQuery(field):
            if field:
                return [r["_source"]["metadata"][field] for r in hits]
            else:
                return [r["_source"] for r in hits]
        else:
            if field:
                if field.startswith("_"):
                    return [r[field] for r in hits]
                else:
                    return [r["_source"][field] for r in hits]
            else:
                return [r["_source"] for r in hits]

    def listRecords(self, conditions=None, field="guid", max_results=sys.maxsize, table=TABLE_PAPERS):
        """
            This is the equivalent of a SELECT clause
        """
        self.checkConnectedToDB()

        es_index = index_equivalence[table]["index"]
        es_type = index_equivalence[table]["type"]

        if conditions:
            query = self.filterQuery(conditions)
        else:
            ##            query=self.filterQuery(field+":*")
            query = self.filterQuery("*:*")

        prev_max_results = self.max_results
        self.max_results = max_results

        hits = self.unlimitedQuery(
            q=query,
            index=es_index,
            doc_type=es_type,
            _source=field,
        )
        self.max_results = prev_max_results

        return self.abstractNestedResults(query, hits, field)

    def listPapers(self, conditions=None, field="guid", max_results=sys.maxsize):
        """
            Return a list of GUIDs in papers table where [conditions]
        """
        return self.listRecords(conditions, field, max_results, "papers")

    def runSingleValueQuery(self, query):
        raise NotImplementedError

    def addAuthor(self, author):
        """
            Make sure author is in database
        """
        self.checkConnectedToDB()

        author["author_id"] = self.generateAuthorID
        self.updateAuthor(author, "create")

    def mergeAuthorDetails(self, author_record, new_author_data):
        """
        """

        def findAffiliation(aff_list, new_aff):
            """
            """
            if new_aff.get("name", "") in ["", None]:
                return None

            for aff in aff_list:
                if aff.get("name", "") == new_aff["name"]:
                    return aff

        def mergeList(new_list, record_list):
            """
                Adds the missing papers from the new_list to to the record_list
            """
            for paper in new_list:
                if paper not in record_list:
                    record_list.append(paper)

        # TODO Fuzzywuzzy this!
        for aff in new_author_data:
            match = findAffiliation(author_record["affiliation"], aff)
            if match:
                mergeList(aff.get("papers", []), match["papers"])
            else:
                author_record["affiliation"].append(aff)

        mergeList(new_author_data["papers"], author_record["papers"])
        mergeList(new_author_data["papers_first_author"], author_record["papers_first_author"])
        mergeList(new_author_data["papers_last_author"], author_record["papers_last_author"])

    def updateAuthorsFromPaper(self, metadata):
        """
            Make sure authors are in database

            :param metadata: a paper's metadata, with an "authors" key
        """
        self.checkConnectedToDB()

        for index, new_author in enumerate(metadata["authors"]):
            creating_new_record = False
            author_record = self.matcher.matchAuthor(new_author)
            if not author_record:
                creating_new_record = True
                author_record = copy.deepcopy(new_author)
                author_record["author_id"] = self.generateAuthorID()
                author_record["papers"] = []
                author_record["papers_first_author"] = []
                author_record["papers_last_author"] = []
                author_record["num_papers"] = 0

            if metadata["guid"] not in author_record["papers"]:
                author_record["papers"].append(metadata["guid"])
                if index == 0:
                    author_record["papers_first_author"].append(metadata["guid"])
                if index == len(metadata["authors"]):
                    author_record["papers_last_author"].append(metadata["guid"])
            author_record["num_papers"] = len(author_record["papers"])

            if not creating_new_record:
                self.mergeAuthorDetails(author_record, new_author)

            self.updateAuthor(author_record, op_type="create" if creating_new_record else "index")

    def updateVenuesFromPaper(self, metadata):
        """
            Progressive update of venues
        """
        raise NotImplementedError

    ##        res=self.es.search(
    ##            index=ES_INDEX_VENUES,
    ##            doc_type=ES_TYPE_VENUE,
    ##            _source=field,
    ##            q="guid:*")
    ##
    ##        return [r["_source"] for r in hits]

    def updateAuthor(self, author, op_type="index"):
        """
            Updates an existing author in the db

            :param author: author data
            :param op_type: one of ["index", "create"]
        """
        self.checkConnectedToDB()

        timestamp = datetime.datetime.now()

        body = {
            "author": author,
        }

        author["time_updated"] = timestamp

        if op_type == "create":
            body["time_created"] = timestamp

        self.es.index(
            index=ES_INDEX_AUTHORS,
            doc_type=ES_TYPE_AUTHOR,
            op_type=op_type,
            id=author["author_id"],
            body=body
        )

    def addPaper(self, metadata, check_existing=True, has_scidoc=True):
        """
            Add paper metadata to database
        """
        op_type = "create" if check_existing else "index"
        self.updatePaper(metadata, op_type, has_scidoc)
        if self.AUTO_ADD_AUTHORS:
            self.updateAuthorsFromPaper(metadata)

    def updatePaper(self, metadata, op_type="index", has_scidoc=None):
        """
            Updates an existing record in the db

            :param metadata: metadata of paper
            :param op_type: one of ["index", "create"]
            :param has_scidoc: True if SciDoc for this paper exists in scidocs \
                index, False otherwise
        """
        self.checkConnectedToDB()

        timestamp = datetime.datetime.now()
        body = {"guid": metadata["guid"],
                "metadata": metadata,
                "norm_title": metadata["norm_title"],
                "num_in_collection_references": metadata.get("num_in_collection_references", 0),
                "num_resolvable_citations": metadata.get("num_resolvable_citations", 0),
                "num_inlinks": len(metadata.get("inlinks", [])),
                "time_modified": timestamp,
                ##                "corpus_id": metadata["corpus_id"],
                ##                "filename": metadata["filename"],
                ##                 "collection_id": metadata["collection_id"],
                ##                "import_id": metadata["import_id"],
                ##                "title": metadata["title"],
                ##                "surnames": metadata["surnames"],
                ##                "year": metadata["year"],
                }

        if has_scidoc is not None:
            body["has_scidoc"] = has_scidoc

        if op_type == "create":
            body["time_created"] = timestamp

        if op_type == "update":
            body = {"doc": body}
            try:
                self.es.update(
                    index=ES_INDEX_PAPERS,
                    doc_type=ES_TYPE_PAPER,
                    id=metadata["guid"],
                    body=body
                )
            except TransportError as e:
                self.es.indices.refresh(index=ES_INDEX_PAPERS)
                self.es.update(
                    index=ES_INDEX_PAPERS,
                    doc_type=ES_TYPE_PAPER,
                    id=metadata["guid"],
                    body=body
                )

        else:
            self.es.index(
                index=ES_INDEX_PAPERS,
                doc_type=ES_TYPE_PAPER,
                op_type=op_type,
                id=metadata["guid"],
                body=body
            )

    def addLink(self, GUID_from, GUID_to, authors_from, authors_to, year_from, year_to, numcitations):
        """
            Add a link in the citation graph.
        """
        self.checkConnectedToDB()

        self.es.create(
            index=ES_INDEX_LINKS,
            doc_type=ES_TYPE_LINK,
            body={
                "guid_from": GUID_from,
                "guid_to": GUID_to,
                "authors_from": authors_from,
                "authors_to": authors_from,
                "year_from": year_from,
                "year_to": year_to,
                "numcitations": numcitations,
                "time_created": datetime.datetime.now(),
            })

    def addMissingPaper(self, metadata):
        """
            Inserts known data about a paper with no SciDoc
        """
        ##        self.addPaper(metadata,check_existing=True,has_scidoc=False)
        raise NotImplementedError

    def createDBindeces(self):
        """
            Call this after importing the metadata into the corpus and before
            matching in-collection references, it should speed up search
        """
        self.checkConnectedToDB()

        for index in ES_ALL_INDECES:
            if self.es.indeces.exists(index=index):
                self.es.optimize(index=index)
        pass

    def deleteAll(self, record_type):
        """
            WARNING! This function deletes all the records in a given "table" or
            of a given type.

            :param record_type: one of ["papers","links","authors","scidocs","cache"]

        """
        self.checkConnectedToDB()

        if record_type not in index_equivalence:
            raise ValueError("Unknown record type")

        es_table = index_equivalence[record_type]["index"]

        if self.es.indices.exists(index=es_table):
            print("Deleting ALL files in %s" % es_table)
            # ignore 404 and 400
            self.deleteIndex(es_table)
            self.createAndInitializeDatabase()

    def deleteIndex(self, pattern):
        """
            Deletes all indexes matching the pattern.

            Warning! Use only if you know exactly what you are doing!
        """
        self.es.indices.delete(index=pattern, ignore=[400, 404])

    def deleteByQuery(self, record_type, query):
        """
            Delete the entries from a table that match the query.

            :param record_type: one of the tables that exist, e.g. ["papers","links","authors","scidocs","cache"]
            :type record_type: string
            :param query: a query to select documents to delete
            :type query: string
        """
        self.checkConnectedToDB()

        if not self.es.indices.exists(index=index_equivalence[record_type]["index"]):
            return

        es_table = index_equivalence[record_type]["index"]
        es_type = index_equivalence[record_type]["type"]

        to_delete = self.unlimitedQuery(
            index=es_table,
            doc_type=es_type,
            q=query)

        self.bulkDelete([item["_id"] for item in to_delete])

    def bulkDelete(self, id_list, table="papers"):
        """
            Deletes all entries in id_list from the given table that match on id.


        """
        self.checkConnectedToDB()

        if not self.es.indices.exists(index=index_equivalence[table]["index"]):
            return

        es_table = index_equivalence[table]["index"]
        es_type = index_equivalence[table]["type"]

        bulk_commands = []
        for item in id_list:
            bulk_commands.append("{ \"delete\" : {  \"_id\" : \"%s\" } }" % item)

        if len(bulk_commands) > 0:
            self.es.bulk(
                body="\n".join(bulk_commands),
                index=es_table,
                doc_type=es_type,
            )

    def unlimitedQuery(self, *args, **kwargs):
        """
            Wraps elasticsearch querying to enable auto scroll for retrieving
            large amounts of results

            It does more or less what elasticsearch.helpers.scan does, only this
            one actually works.
        """
        scroll_time = "20m"

        size = min(self.max_results, 10000)

        res = self.es.search(
            *args,
            size=size,
            search_type="scan",
            scroll=scroll_time,
            **kwargs
        )

        results = res['hits']['hits']
        scroll_size = res['hits']['total']
        while (scroll_size > 0) and len(results) < self.max_results:
            try:
                scroll_id = res['_scroll_id']
                rs = self.es.scroll(scroll_id=scroll_id, scroll=scroll_time)
                res = rs
                results.extend(rs['hits']['hits'])
                scroll_size = len(rs['hits']['hits'])
            except:
                break

        return results[:self.max_results]

    def setCorpusFilter(self, collection_id=None, import_id=None, date=None):
        """
            Sets the filter query to limit all queries to a collection (corpus)
            or an import date

            :param collection: identifier of corpus, e.g. "ACL" or "PMC". This is set at import time.
            :type collection:basestring
            :param import: identifier of import, e.g. "initial"
            :type import:basestring
            :param date: comparison with a date, e.g. ">[date]", "<[date]",
            :type collection:basestring
        """
        query_items = []
        if collection_id:
            query_items.append("metadata.collection_id:\"%s\"" % collection_id)
        if import_id:
            query_items.append("metadata.import_id:\"%s\"" % import_id)
        if date:
            query_items.append("time_created:%s" % date)

        self.query_filter = " AND ".join(query_items) + " AND "


DOCTEST = False

if __name__ == '__main__':

    if DOCTEST:
        import doctest

        doctest.testmod(optionflags=doctest.NORMALIZE_WHITESPACE)
