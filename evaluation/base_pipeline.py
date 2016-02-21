# Testing pipeline classes
#
# Copyright:   (c) Daniel Duma 2015
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import print_function

import glob, math, os, re, sys, gc, random, json
from copy import deepcopy
from collections import defaultdict, namedtuple, OrderedDict

from base_retrieval import BaseRetrieval, MAX_RESULTS_RECALL

import minerva.db.corpora as cp
from minerva.proc.results_logging import ProgressIndicator, ResultsLogger
from minerva.proc.nlp_functions import AZ_ZONES_LIST, CORESC_LIST, RANDOM_ZONES_7, RANDOM_ZONES_11
from minerva.proc.general_utils import getSafeFilename, exists, ensureDirExists

def analyticalRandomChanceMRR(numinlinks):
    """
        Returns the MRR score based on analytical random chance
    """
    res=0
    for i in range(numinlinks):
        res+=(1/float(numinlinks))*(1/float(i+1))
    return res


def getDictOfTestingMethods(methods):
    """
        Make a simple dictionary of {method_10:{method details}}

        new: prepare for using a single Lucene index with fields for the parameters
    """
    res=OrderedDict()
    for method in methods:
        for parameter in methods[method]["parameters"]:
            if methods[method]["type"] in ["standard_multi","inlink_context"]:
                addon="_"+str(parameter)
                indexName=method+addon
                res[indexName]=deepcopy(methods[method])
                res[indexName]["method"]=method
                res[indexName]["parameter"]=parameter
                res[indexName]["index_filename"]= methods[method]["index"]+addon
                res[indexName]["runtime_parameters"]=methods[method]["runtime_parameters"]
##                res[indexName]["index_field"]=str(parameter)
            elif methods[method]["type"] in ["ilc_mashup"]:
                for ilc_parameter in methods[method]["ilc_parameters"]:
                    addon="_"+str(parameter)+"_"+str(ilc_parameter)
                    indexName=method+addon
                    res[indexName]=deepcopy(methods[method])
                    res[indexName]["method"]=method
                    res[indexName]["parameter"]=parameter
                    res[indexName]["ilc_parameter"]=ilc_parameter
                    res[indexName]["index_filename"]=methods[method]["index"]+addon
                    res[indexName]["runtime_parameters"]=methods[method]["runtime_parameters"]
##                    res[indexName]["index_field"]=str(parameter)+"_"+str(ilc_parameter)
            elif methods[method]["type"] in ["annotated_boost"]:
                for runtime_parameter in methods[method]["runtime_parameters"]:
                    indexName=method+"_"+str(parameter)+"_"+runtime_parameter
                    res[indexName]=deepcopy(methods[method])
                    res[indexName]["method"]=method
                    res[indexName]["parameter"]=parameter
                    res[indexName]["runtime_parameters"]= methods[method]["runtime_parameters"][runtime_parameter]
##                    res[indexName]["index_filename"]=methods[method]["index"]+"_"+str(parameter)
                    res[indexName]["index_filename"]=methods[method]["index"]+"_"+str(parameter)
            elif methods[method]["type"] in ["ilc_annotated_boost"]:
                for ilc_parameter in methods[method]["ilc_parameters"]:
                    for runtime_parameter in methods[method]["runtime_parameters"]:
                        indexName=method+"_"+str(ilc_parameter)+"_"+runtime_parameter
                        res[indexName]=deepcopy(methods[method])
                        res[indexName]["method"]=method
                        res[indexName]["parameter"]=parameter
                        res[indexName]["runtime_parameters"]=methods[method]["runtime_parameters"][runtime_parameter]
                        res[indexName]["ilc_parameter"]=ilc_parameter
                        res[indexName]["index_filename"]=methods[method]["index"]+"_"+str(parameter)+"_"+str(ilc_parameter)
##                    res[indexName]["index_field"]=str(parameter)+"_"+str(ilc_parameter)
    return res


class BasePipeline(object):
    """
        Base class for testing pipelines
    """
    def __init__(self, retrieval_class=BaseRetrieval):
        # This points to the the class of retrieval we are using
        self.retrieval_class=retrieval_class
        pass

    def loadModel(self, guid):
        """
        """
        for model in self.files_dict[guid]["tfidf_models"]:
            # create a Lucene search instance for each method
            self.tfidfmodels[model["method"]]=self.retrieval_class(
                model["actual_dir"],
                model["method"],
                logger=None,
                use_default_similarity=exp["use_default_similarity"])

    def generateRetrievalModels(self, all_doc_methods, all_files,):
        """
            Generates the files_dict with the paths to the retrieval models
        """
        for guid in all_files:
            self.files_dict[guid]["tfidf_models"]=[]
            for method in all_doc_methods:
                actual_dir=cp.Corpus.getRetrievalIndexPath(guid,all_doc_methods[method]["index_filename"],self.exp["full_corpus"])
                self.files_dict[guid]["tfidf_models"].append({"method":method,"actual_dir":actual_dir})

    def addRandomControlResult(self, guid, precomputed_query, doc_method):
        """
             Adds a result that is purely based on analytical chance, for
             comparison.
        """
        result_dict={"file_guid":guid,
            "citation_id":precomputed_query["citation_id"],
            "doc_position":precomputed_query["doc_position"],
            "query_method":precomputed_query["query_method"],
            "doc_method":doc_method ,
            "match_guid":precomputed_query["match_guid"],
            "doc_method":"RANDOM",
            "mrr_score":analyticalRandomChanceMRR(self.files_dict[guid]["in_collection_references"]),
            "precision_score":1/float(self.files_dict[guid]["in_collection_references"]),
            "ndcg_score":0,
            "rank":0,
            "first_result":""
            }

        # Deal here with CoreSC/AZ/CFC annotation
        for annotation in self.exp.get("rhetorical_annotations",[]):
            result_dict[annotation]=precomputed_query.get(annotation)

        self.logger.addResolutionResultDict(result_dict)


    def initializePipeline(self):
        """
            Whatever needs to happen before we start the pipeline: inializing
            connections, VMs, whatever.

            This function should be overriden by descendant classes if anything
            is to be done.
        """
        if self.retrieval_class.__name__.startswith("Lucene"):
            import lucene
            try:
                lucene.initVM(maxheap="640m") # init Lucene VM
            except ValueError:
                # VM already up
                print(sys.exc_info()[1])

    def startLogging(self):
        """
        """
        output_filename=os.path.join(self.exp["exp_dir"],self.exp.get("output_filename","results.csv"))
        self.logger=ResultsLogger(False,dump_filename=output_filename) # init all the logging/counting
        self.logger.startCounting() # for timing the process, start now

    def loadQueriesAndFileList(self):
        """
        """
        precomputed_queries_file_path=self.exp.get("precomputed_queries_file_path",None)
        if not precomputed_queries_file_path:
            precomputed_queries_file_path=os.path.join(self.exp["exp_dir"],self.exp.get("precomputed_queries_filename","precomputed_queries.json"))
        self.precomputed_queries=json.load(open(precomputed_queries_file_path,"r"))
        files_dict_filename=os.path.join(self.exp["exp_dir"],self.exp.get("files_dict_filename","files_dict.json"))
        self.files_dict=json.load(open(files_dict_filename,"r"))

    def populateMethods(self):
        """
            Fills dict with all the test methods, parameters and options, including
            the retrieval instances
        """
        self.tfidfmodels={}
        all_doc_methods=None

        if self.exp.get("doc_methods", None):
            all_doc_methods=getDictOfTestingMethods(self.exp["doc_methods"])
            # essentially this overrides whatever is in files_dict, if testing_methods was passed as parameter

            if self.exp["full_corpus"]:
                all_files=["ALL_FILES"]
            else:
                all_files=self.files_dict.keys()

            self.generateRetrievalModels(all_doc_methods,all_files)
        else:
            all_doc_methods=self.files_dict["ALL_FILES"]["doc_methods"] # load from files_dict

        if self.exp["full_corpus"]:
            for model in self.files_dict["ALL_FILES"]["tfidf_models"]:
                # create a Lucene search instance for each method
                self.tfidfmodels[model["method"]]=self.retrieval_class(model["actual_dir"],model["method"],logger=None, use_default_similarity=self.exp["use_default_similarity"])

        self.main_all_doc_methods=all_doc_methods

    def newResultDict(self, guid, precomputed_query, doc_method):
        """
        """
        result_dict={"file_guid":guid,
        "citation_id":precomputed_query["citation_id"],
        "doc_position":precomputed_query["doc_position"],
        "query_method":precomputed_query["query_method"],
        "doc_method":doc_method ,
        "match_guid":precomputed_query["match_guid"]}

        # Deal here with CoreSC/AZ/CFC annotation
        for annotation in self.exp.get("rhetorical_annotations",[]):
            result_dict[annotation]=precomputed_query.get(annotation)

        return result_dict

    def addEmptyResult(self, guid, precomputed_query, doc_method):
        """
        """
        result_dict=self.newResultDict(guid, precomputed_query, doc_method)
        result_dict["mrr_score"]=0
        result_dict["precision_score"]=0
        result_dict["ndcg_score"]=0
        result_dict["rank"]=0
        result_dict["first_result"]=""
        self.logger.addResolutionResultDict(result_dict)

    def addResult(self, guid, precomputed_query, doc_method, retrieved):
        """
        """
        result_dict=self.newResultDict(guid, precomputed_query, doc_method)
        result=self.logger.measureScoreAndLog(retrieved, precomputed_query["citation_multi"], result_dict)
##        rank_per_method[result["doc_method"]].append(result["rank"])
##        precision_per_method[result["doc_method"]].append(result["precision_score"])

    def logTextAndReferences(self):
        """
            Extra logging, not used right now
        """
        pre_selection_text=doctext[queries[qmethod]["left_start"]-300:queries[qmethod]["left_start"]]
        draft_text=doctext[queries[qmethod]["left_start"]:queries[qmethod]["right_end"]]
        post_selection_text=doctext[queries[qmethod]["right_end"]:queries[qmethod]["left_start"]+300]
        draft_text=u"<span class=document_text>{}</span> <span class=selected_text>{}</span> <span class=document_text>{}</span>".format(pre_selection_text, draft_text, post_selection_text)
##        print(draft_text)

    def computeStatistics():
        """
        """
        rank_diff=abs(rank_per_method["section_1_full_text"][-1]-rank_per_method["full_text_1"][-1])
##        if method_overlap_temp["section_1_full_text"] == method_overlap_temp["full_text_1"]
        if rank_diff == 0:
            methods_overlap+=1
        rank_differences.append(rank_diff)
        total_overlap_points+=1


    def runPipeline(self, exp):
        """
            Using Lucene, run Citation Resolution
            Load everything from precomputed queries
        """
        self.exp=exp

        self.startLogging()
        self.initializePipeline()
        self.loadQueriesAndFileList()
        self.logger.setNumItems(len(self.precomputed_queries))
        self.populateMethods()

##        methods_overlap=0
##        total_overlap_points=0
##        rank_differences=[]
##        rank_per_method=defaultdict(lambda:[])
##        precision_per_method=defaultdict(lambda:[])

        # this is for counting overlaps only
        previous_guid=""

        #=======================================
        # MAIN LOOP over all precomputed queries
        #=======================================
        for precomputed_query in self.precomputed_queries:
            guid=precomputed_query["file_guid"]
            self.logger.total_citations+=self.files_dict[guid]["resolvable_citations"]

            all_doc_methods=deepcopy(self.main_all_doc_methods)

            if not exp["full_corpus"] and guid != previous_guid:
                previous_guid=guid
                self.loadModel(guid)

            # create a dict where every field gets a weight of 1
            for method in self.main_all_doc_methods:
                all_doc_methods[method]["runtime_parameters"]={x:1 for x in self.main_all_doc_methods[method]["runtime_parameters"]}

            # for every method used for extracting BOWs
            for doc_method in all_doc_methods:
                # ACTUAL RETRIEVAL HAPPENING - run query
                self.logger.logReport("Citation: "+precomputed_query["citation_id"]+"\n Query method:"+precomputed_query["query_method"]+" \nDoc method: "+doc_method +"\n")
                self.logger.logReport(precomputed_query["query_text"]+"\n")

                retrieved=self.tfidfmodels[doc_method].runQuery(
                    precomputed_query["structured_query"],
                    all_doc_methods[doc_method]["runtime_parameters"],
                    guid,
                    max_results=exp.get("max_results_recall",MAX_RESULTS_RECALL))

                if not retrieved:    # the query was empty or something
                    self.addEmptyResult(guid, precomputed_query, doc_method)
                else:
                    self.addResult(guid, precomputed_query, doc_method, retrieved)

            if False:
                self.logTextAndReferences()
            if self.exp.get("add_random_control_result", False):
                self.addRandomControlResult(guid, precomputed_query, doc_method)

            self.logger.showProgressReport(guid) # prints out info on how it's going
##            self.computeStatistics()

        self.logger.writeDataToCSV()
        self.logger.showFinalSummary()


class CompareExplainPipeline(BasePipeline):
    """
    """
    def __init__(self):
        pass

    def populateMethods(self):
        """
        """
        super(LuceneTestingPipeline, self).populateMethods()

        if self.exp.get("compare_explain",False):
            for method in self.main_all_doc_methods:
                self.main_all_doc_methods[method+"_EXPLAIN"]=self.main_all_doc_methods[method]

    def loadModel(self, model, exp):
        """
        """
        super(LuceneTestingPipeline, self).loadModel(model, exp)

        # this is to compare bulkScorer and .explain() on their overlap
        self.tfidfmodels[model["method"]+"_EXPLAIN"]=self.retrieval_class(
            model["actual_dir"],
            model["method"],
            logger=None,
            use_default_similarity=exp["use_default_similarity"])
        self.tfidfmodels[model["method"]+"_EXPLAIN"].useExplainQuery=True

class PrecomputedPipeline(BasePipeline):
    """
        class comment
    """

    def __init__(self):
        pass

    def runPrecomputedQuery(self, retrieval_result, parameters):
        """
            This takes a query that has already had the results added
        """
        scores=[]
        for unique_result in retrieval_result:
            formula=storedFormula(unique_result["formula"])
            score=formula.computeScore(parameters)
            scores.append((score,{"guid":unique_result["guid"]}))

        scores.sort(key=lambda x:x[0],reverse=True)
        return scores


    def measurePrecomputedResolution(retrieval_results,method,parameters, citation_az="*"):
        """
            This is kind of like measureCitationResolution:
            it takes a list of precomputed retrieval_results, then applies the new
            parameters to them. This is how we recompute what Lucene gives us,
            avoiding having to call Lucene again.

            All we need to do is adjust the weights on the already available
            explanation formulas.
        """
        logger=ResultsLogger(False, dump_straight_to_disk=False) # init all the logging/counting
        logger.startCounting() # for timing the process, start now

        logger.setNumItems(len(retrieval_results),print_out=False)

        # for each query-result: (results are packed inside each query for each method)
        for result in retrieval_results:
            # select only the method we're testing for
            res=result["results"]
            retrieved=self.runPrecomputedQuery(res,parameters)

            result_dict={"file_guid":result["file_guid"],
            "citation_id":result["citation_id"],
            "doc_position":result["doc_position"],
            "query_method":result["query_method"],
            "doc_method":method,
            "az":result["az"],
            "cfc":result["cfc"],
            "match_guid":result["match_guid"]}

            if not retrieved or len(retrieved)==0:    # the query was empty or something
                score=0
                precision_score=0
    ##                        print "Error: ", doc_method , qmethod,tfidfmodels[method].indexDir
    ##                        logger.addResolutionResult(guid,m,doc_position,qmethod,doc_method ,0,0,0)
                result_dict["mrr_score"]=0
                result_dict["precision_score"]=0
                result_dict["ndcg_score"]=0
                result_dict["rank"]=0
                result_dict["first_result"]=""

                logger.addResolutionResultDict(result_dict)
            else:
                result=logger.measureScoreAndLog(retrieved, result["citation_multi"], result_dict)

        logger.computeAverageScores()
        results=[]
        for query_method in logger.averages:
            for doc_method in logger.averages[query_method]:
    ##            weights=all_doc_methods[doc_method]["runtime_parameters"]
                weights=parameters
                data_line={"query_method":query_method,"doc_method":doc_method,"citation_az":citation_az}

                for metric in logger.averages[query_method][doc_method]:
                    data_line["avg_"+metric]=logger.averages[query_method][doc_method][metric]
                data_line["precision_total"]=logger.scores["precision"][query_method][doc_method]

                signature=""
                for w in weights:
                    data_line[w]=weights[w]
                    signature+=str(w)

    ##            data_line["weight_signature"]=signature
                results.append(data_line)

    ##    logger.writeDataToCSV(cp.cp.Corpus.dir_output+"testing_test_precision.csv")

        return results



def main():
    pass

if __name__ == '__main__':
    main()