# AZ classification
#
# Copyright:   (c) Daniel Duma 2014
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import absolute_import
from __future__ import print_function

import os, sys


import glob

import nltk
import nltk.classify.util
import nltk.metrics
import six.moves.cPickle

from scidoc.xmlformats.azscixml import *


if __name__ == "__main__" and __package__ is None:
    __package__ = "az"

PACKAGE_PARENT = '..'
SCRIPT_DIR = os.path.dirname(os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__))))
sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))
sys.path.append("/Users/masterman/Dropbox/PhD/minerva3/minerva/az/")

from az_features import buildAZFeatureSetForDoc

# For maxent training
MIN_LL_DELTA = 0.0005  # minimum increment per step
MAX_ITER = 30  # max number of iterations for training


def buildGlobalFeatureset(input_mask, output_file):
    """
        Creates a list of all sentences in the collections, their features and class,
        for classifier training/testing
    """
    doc_list = glob.glob(input_mask)
    global_featureset = []

    for filename in doc_list:
        doc = SciDoc(filename)
        featureset = buildAZFeatureSetForDoc(doc)
        global_featureset.extend(featureset)

    output_dir=os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    six.moves.cPickle.dump(global_featureset, open(output_file, "wb"))
    return global_featureset


# ===============================
#       TESTING CODE
# ===============================
# drive = "C"
# global_featureset_filename = drive + r":\nlp\phd\raz\converted_scidoc_files\global_featureset.pickle"
# input_mask = drive + r":\nlp\phd\raz\converted_scidoc_files\*.json"

global_featureset_filename =  r"/Users/masterman/NLP/PhD/raz/converted_scidoc_files/global_featureset.pickle"
input_mask = r"/Users/masterman/NLP/PhD/raz/converted_scidoc_files/*.json"

def runTestAZ(rebuild=False):
    if rebuild:
        print("Rebuilding global featureset")
        global_featureset = buildGlobalFeatureset(input_mask, global_featureset_filename)
    else:
        global_featureset = six.moves.cPickle.load(open(global_featureset_filename))

    train_set = global_featureset[:len(global_featureset) / 10]
    test_set = global_featureset[len(global_featureset) / 10:]

    print("Training classifier")
    classifier = nltk.MaxentClassifier.train(train_set, min_lldelta=MIN_LL_DELTA, max_iter=MAX_ITER)
    ##    classifier = nltk.NaiveBayesClassifier.train(train_set)
    print("Accuracy:", nltk.classify.accuracy(classifier, test_set))

    classified = [classifier.classify(x[0]) for x in test_set]

    cm = nltk.ConfusionMatrix([x[1] for x in test_set], classified)
    print(cm.pp(sort_by_count=True, show_percents=True, truncate=9))


def runKFoldCrossValidation(rebuild=False, folds=3):
    """
        Tests the classifier with K-fold cross-validation

    """
    from sklearn import model_selection

    if rebuild:
        print("Rebuilding global featureset")
        global_featureset = buildGlobalFeatureset(input_mask, global_featureset_filename)
    else:
        global_featureset = six.moves.cPickle.load(open(global_featureset_filename, "rb"))

    cv = model_selection.KFold(n_splits=folds, shuffle=False, random_state=None)
    # cv=zip(cv.split(global_featureset))
    accuracies = []

    print("Beginning", folds, "-fold cross-validation")

    for traincv, testcv in cv.split(global_featureset):
        ##        print "Training classifier"
        ##        print traincv,testcv
        ##        print traincv[0],":",traincv[-1]
        ##        print testcv[0],":",testcv[-1]

        train_set = [global_featureset[i] for i in traincv]
        test_set = [global_featureset[i] for i in testcv]

        # select type of classifier here
        ##        classifier = nltk.NaiveBayesClassifier.train(train_set)
        classifier = nltk.MaxentClassifier.train(global_featureset[traincv[0]:traincv[len(traincv) - 1]],
                                                 min_lldelta=MIN_LL_DELTA, max_iter=MAX_ITER)

        accuracy = nltk.classify.util.accuracy(classifier, test_set)
        print('accuracy:', accuracy)
        accuracies.append(accuracy)
        classified = [classifier.classify(x[0]) for x in test_set]
        cm = nltk.ConfusionMatrix([x[1] for x in test_set], classified)
        print(cm.pp(sort_by_count=True, show_percents=True, truncate=9))

    print("average accuracy:", sum(accuracies) / float(len(accuracies)))


def trainAZfullCorpus(filename, rebuild=False):
    """
        Trains and saves an AZ classifier for the full corpus, saves it in filename
    """
    if rebuild:
        print("Rebuilding global featureset")
        global_featureset = buildGlobalFeatureset(input_mask, global_featureset_filename)
    else:
        global_featureset = six.moves.cPickle.load(open(global_featureset_filename))

    classifier = nltk.MaxentClassifier.train(global_featureset, min_lldelta=MIN_LL_DELTA, max_iter=MAX_ITER)
    six.moves.cPickle.dump(classifier, open(filename, "wb"))


def main():
    ##    convertAnnotToSciDoc(r"g:\NLP\PhD\raz\input\*.annot",r"C:\NLP\PhD\raz\converted_scidoc_files")

    ##    doc=SciDoc()
    ##    doc=loadAZSciXML(r"g:\nlp\phd\raz\input\9405001.annot")
    ##    featureset=buildFeatureSetForDoc(doc)

    ##    runTestAZ(True)
    runKFoldCrossValidation(False, 5)


##    trainAZfullCorpus("trained_az_classifier.pickle",True)

##    doc.saveToFile(r"c:\nlp\raz\converted_scidoc_files\9405001.json")


if __name__ == '__main__':
    main()
