# Experiments with the ACL corpus like the ones for LREC'16
#
# Copyright:   (c) Daniel Duma 2016
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import absolute_import
from __future__ import print_function

import db.corpora as cp
from evaluation.experiment import Experiment
from proc.general_utils import getRootDir

# BOW files to prebuild for generating document representation.
prebuild_bows = {
    ##"full_text":{"function":"getDocBOWfull", "parameters":[1]},
    "az_annotated": {"function": "getDocBOWannotated", "parameters": [1]},
}

# bow_name is just about the name of the file containing the BOWs
prebuild_indeces = {
}

# the name of the index is important, should be unique
prebuild_general_indexes = {
    ##    "az_annotated_pmc_2013":{"type":"ilc_mashup",
    ##                             "bow_name":"ilc_annotated", # bow to load
    ##                             "ilc_method":"ilc_annotated", # bow to load
    ##                             "mashup_method":"az_annotated",
    ##                             "ilc_parameters":["paragraph"], # parameter has to match a parameter of a prebuilt bow
    ##                             "parameters":[1], # parameter has to match a parameter of a prebuilt bow
    ##                             "max_year":2013 # cut-off point for adding files to index
    ##                             },
    "az_annotated_pmc_2013": {"type": "standard_multi",
                              "bow_name": "az_annotated",  # bow to load
                              "parameters": [1],  # parameter has to match a parameter of a prebuilt bow
                              "max_year": 2013  # cut-off point for adding files to index
                              },
}

doc_methods = {
    "full_text": {"type": "standard_multi", "index": "az_annotated_pmc_2013", "parameters": [1],
                  "runtime_parameters": ["_full_text"]},
}

# this is the dict of query extraction methods
qmethods = {

    ##        "window":{"parameters":[
    ##                (3,3),
    ##                (5,5),
    ##                (10,10),
    ##                (5,10),
    ##                (10,5),
    ##                (20,20),
    ##                (20,10),
    ##                (10,20),
    ##                (30,30),
    ##                (50,50),
    ##                (100,100),
    ##                (500,500),
    ##                ],
    ##                "method":"Window",
    ##                },

    "sentence": {"parameters": [
        ##                "1only",
        ##                "paragraph",
        ##                "1up",
        ##                "0up_1down",
        ##                "1up_1down",
        ##                "2up_2down",
        "2up_2down"
    ],
        "method": "Sentences",
    },

    ##            "annotated_sentence":{"parameters":[
    ##                "pno",
    ##                "po",
    ##                "no",
    ##                "n",
    ##                "p",
    ##                ],
    ##                "method":"SelectedSentences",
    ##                },

}

experiment = {
    "name": "pmc_annotated_kw",
    "description":
        "Full-text indexing of PMC to test kw extraction",
    # dict of bag-of-word document representations to prebuild
    "prebuild_bows": prebuild_bows,
    # dict of per-file indexes to prebuild
    "prebuild_indeces": prebuild_indeces,
    # dict of general indexes to prebuild
    "prebuild_general_indexes": prebuild_general_indexes,
    # dictionary of document representation methods to test
    "doc_methods": doc_methods,
    # dictionary of query generation methods to test
    "qmethods": qmethods,
    # list of files in the test set
    "test_files": [],
    # SQL condition to automatically generate the list above
    "test_files_condition": "metadata.num_in_collection_references:>0 AND metadata.year:>2013",
    # This lets us pick just the first N files
    "max_test_files": 1500,
    # Use Lucene DefaultSimilarity? As opposed to FieldAgnosticSimilarity
    "use_default_similarity": True,

    # Annotate sentences with AZ/CoreSC/etc?
    "rhetorical_annotations": [],
    # Run annotators? If False, it is assumed the sentences are already annotated
    "run_rhetorical_annotators": False,
    # Separate queries by AZ/CSC, etc?
    "use_rhetorical_annotation": False,
    ##    "weight_values":[],
    # use full-collection retrival? If False, it runs "citation resolution"
    "full_corpus": True,
    # "compute_once", "train_weights", "extract_kw"
    "type": "extract_kw",
    # If full_corpus, this is the cut-off year for including documents in the general index.
    # In this way we can separate test files and retrieval files.
    "index_max_year": 2013,
    # how many chunks to split each file for statistics on where the citation occurs
    "numchunks": 10,
    # name of CSV file to save results in
    "output_filename": "results.csv",
    "pivot_table": "",
    "max_results_recall": 200,
    # should queries be classified based on some rhetorical class of the sentence: "az", "csc_type", "" or None
    "queries_classification": "",
    # do not process more than this number of queries of the same type (type on line above)
    "max_per_class_results": 1000,
    # of all precomputed queries, which classes should be processed/evaluated?
    "queries_to_process": ["ALL"],
    # what "zones" to try to train weights for
    "train_weights_for": [],  # ["Bac"], ["Hyp","Mot","Bac","Goa","Obj","Met","Exp","Mod","Obs","Res","Con"]
    # add another doc_method showing the score based on analytical random chance?
    "add_random_control_result": False,
    "precomputed_queries_filename": "precomputed_queries.json",
    "files_dict_filename": "files_dict.json",

    # what to extract as a citation's context
    "context_extraction": "sentence",
    "context_extraction_parameter": "2up_2down",

    # how to choose the top keywords for a citation
    "keyword_selector": "NBestSelector",
    # parameters to keyword selection method
    "keyword_selection_parameters": {"N": 10},
    # exact name of index to use for extracting idf scores etc. for document feature annotation
    "features_index_name": "idx_az_ilc_az_annotated_pmc_2014_1_paragraph",
    # this is the classifier type we are training
    "keyword_extractor_class": "SKLearnExtractor",
    # this is the classifier subtype. In the case of sklearn, which actual classifier
    "keyword_extractor_subclass": "RandomForestClassifier",
    # parameters for the extractor
    # "keyword_extractor_parameters": {"verbose":True, "hidden_layer_sizes":(100, 50)},
    "keyword_extractor_parameters": {"verbose": True},
    # how many folds to use for training/evaluation
    "cross_validation_folds": 4,
    # an upper limit on the number of data points to use
    ##    "max_data_points": 50000,
}

options = {
    "run_prebuild_bows": 0,  # should the whole BOW building process run?
    "overwrite_existing_bows": 0,  # if a BOW exists already, should we overwrite it?
    "rebuild_indexes": 0,  # rebuild indices?
    "generate_queries": 1,  # precompute the queries?
    "overwrite_existing_queries": 1,  # force rebuilding of queries too?

    "clear_existing_prr_results": 1,  # delete previous precomputed results? i.e. start from scratch
    "run_precompute_retrieval": 1,
    # only applies if type == "train_weights" or "extract_kw". This is necessary for run_feature_annotation! And this is because each pipeline may do different annotation
    "run_feature_annotation": 0,
# annotate scidocs with document-wide features for keyword extraction? By default, False
    "refresh_results_cache": 1,  # should we clean the offline reader cache and redownload it all from elastic?
    "run_experiment": 1,  # must be set to 1 for "run_package_features" to work
    "run_package_features": 1,
    # should we read the cache and repackage all feature information, or use it if it exists already?
    "start_at": 0,
    "list_missing_files": 1,
}


def main():
    from multi.celery_app import MINERVA_ELASTICSEARCH_ENDPOINT

    root_dir = getRootDir("pmc_coresc")
    cp.useElasticCorpus()

    cp.Corpus.connectCorpus(root_dir, endpoint=MINERVA_ELASTICSEARCH_ENDPOINT)
    cp.Corpus.setCorpusFilter("PMC_CSC")
    ##    experiment["test_files"]=["456f8c80-9807-46a9-8455-cd4a7e346f9d"]

    exp = Experiment(experiment, options, False)
    exp.run()


if __name__ == '__main__':
    main()
