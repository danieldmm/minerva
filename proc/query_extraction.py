# functions to extract a citation's context as a query
#
# Copyright:   (c) Daniel Duma 2014
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import print_function

import re, copy
from collections import defaultdict, OrderedDict
from string import punctuation

from nlp_functions import (tokenizeText, tokenizeTextAndRemoveStopwords, stemText, stopwords, stemTokens,
CITATION_PLACEHOLDER, unTokenize, ESTIMATED_AVERAGE_WORD_LENGTH, removeCitations,
PAR_MARKER, CIT_MARKER, BR_MARKER, AZ_ZONES_LIST, CORESC_LIST, formatSentenceForIndexing,
getDictOfTokenCounts, removeStopwords)

from minerva.az.az_cfc_classification import AZ_ZONES_LIST, CORESC_LIST
import minerva.db.corpora as cp

# this is for adding fields to a document in Lucene. These fields are not to be indexed
FIELDS_TO_IGNORE=["left_start","right_end","params","guid_from","year_from", "query_method_id"]


def getFieldSpecialTestName(fieldname, test_guid):
    """
        Returns the name of a "Special" test field. This is to enable splitting
        training data and testing data while at the same time
    """
    return fieldname+"_special_"+test_guid


def selectSentencesToAdd(docfrom,cit,param):
    """
        Returns a list of sentences to include based on the [param]

        Args:
            docfrom: SciDoc we are extracting from
            cit: citation dict
            param: ["paragraph", "1only", "[n]up_[n]down[_crosspar]"]
    """
    sent=docfrom.element_by_id[cit["parent_s"]]
    para=docfrom.element_by_id[sent["parent"]]

    match=re.search(r"(?:(?:(\d)up)_?(?:(\d)down)?(_withinpara)?)|(paragraph)|(1only)",param)
    assert(match)

    context={"ilc_AZ_"+zone:"" for zone in AZ_ZONES_LIST}
    for zone in CORESC_LIST:
        context["ilc_CSC_"+zone]=""
    to_add=[]

    if match.group(4): # paragraph
        to_add=para["content"]
    elif match.group(5): # 1only
        to_add=[cit["parent_s"]]
    else:               #1up_1down, etc
        sent_up=int(match.group(1)) if match.group(1) else 0
        sent_down=int(match.group(2)) if match.group(2) else 0
        within_par=int(match.group(3) != None)


        if not within_par:
            all_sentence_ids=[s["id"] for s in docfrom.allsentences]
        else:
            all_sentence_ids=para["content"]

        index=all_sentence_ids.index(cit["parent_s"])
        if index > 0:
            to_add.extend(all_sentence_ids[index-sent_up:index])

        to_add.append(cit["parent_s"])

        if index < len(docfrom.allsentences)-1:
            to_add.extend(all_sentence_ids[index+1:index+1+sent_down])

    return to_add

class BaseQueryExtractor(object):
    """
        Base class for all query extractors. Implements functions for generating
        the StructuredQuery

        Main entry points:
            .extract()
    """

    def __init__(self):
        pass

    def cleanupQuery(self,query):
        """
            Remove symbols from the query that can lead to errors when parsing the query
        """
        rep_list=["~","^","\"","+","-","(",")", "{","}","[","]","?",":","*"]
        rep_list.extend(punctuation)
        query=query.lower()
        for r in rep_list:
            query=query.replace(r," ")
        query=re.sub(r"\s+"," ",query)
        query=query.strip()
        return query

    def makeStructuredToken(self, token, count, boost=1, bool=None, field=None, distance=None):
        """
            Returns a StructuredToken dict from parameters.
        """
        query_token={
                "token":token,
                "count":count,
                "boost":boost,
                "bool":bool, # +/-
                "field":field,
                "distance": distance
                }
        return query_token

    def filterTokens(self, tokens):
        """
            Removes single numbers that should not be in a query
        """
        res=[]
        rx_bad_token=re.compile(r"\d+")
        for t in tokens:
            if not rx_bad_token.match(t):
                res.append(t)
        return res

    def generateStructuredQuery(self, query_text):
        """
            Default query generator.

            Converts a string/list of tokens to a StructuredQuery

            Args:
                query_text: all the tokens
            Returns:
                intermediate_query: a list of token data
        """
        original_query=query_text
        query_text=self.cleanupQuery(query_text)
        if query_text=="":
            return None

        tokens=tokenizeTextAndRemoveStopwords(query_text)
        tokens=self.filterTokens(tokens)
        query_tokens=getDictOfTokenCounts(tokens)

        res=[]
        for token in query_tokens:
            res.append(self.makeStructuredToken(token, query_tokens[token]))

        return res

    def methodName(self, params):
        """
            Returns the identification string for the current combination of parameters
        """
        current_parameter=params["current_parameter"]
        if isinstance(current_parameter,list) or isinstance(current_parameter,tuple):
            return "%s%d_%d" % (params["method_name"],current_parameter[0],current_parameter[1])
        elif isinstance(current_parameter,basestring):
            return "%s_%s" % (params["method_name"],current_parameter)
        else:
            raise NotImplementedError

    def extract(self, params):
        """
            Must return a fully-formed query for each parameter combination

            Args:
                params: dict with all parameters
        """
        raise NotImplementedError


class WindowQueryExtractor(BaseQueryExtractor):
    """
        Standard Window extractor
    """

    def tokenizeContext(self, params):
        """
            Optimize the extraction of context by limiting the amount of characters and pre-tokenizing
        """
        doctext=params["doctext"]
        left_start=max(0,params["match_start"]-((params["wleft"]+15)*ESTIMATED_AVERAGE_WORD_LENGTH))
        right_end=params["match_end"]+((params["wright"]+15)*ESTIMATED_AVERAGE_WORD_LENGTH)

        left=doctext[left_start:params["match_start"]] # tokenize!
        left=tokenizeText(removeCitations(left))
        left=removeStopwords(left)

        right=doctext[params["match_end"]:right_end] # tokenize!
        right=tokenizeText(removeCitations(right))
        right=removeStopwords(right)

        return {"left":left,"right":right,"left_start":left_start,"right_end":right_end}

    def joinCitationContext(self, leftwords, rightwords, extract_dict):
        """
            Joins the words to the left and to the right of a citation into one
            string.

            Args:
                leftwords: list of tokens
                rightwords: list of tokens
            Returns:
                dict{text: concatenated context}
        """
        assert isinstance(leftwords,list)
        assert isinstance(rightwords,list)
        allwords=[]
        allwords.extend(leftwords)
        allwords.extend(rightwords)
        allwords=[token for token in allwords if token.lower() not in stopwords]
        # Always convert in-text citations to placeholders
        extract_dict["text"]=re.sub(r"<CIT ID=(.*?)\s?/>",CITATION_PLACEHOLDER, unTokenize(allwords))
        return extract_dict

    def selectTokensFromContext(self, context, params):
        """
            Selects the actual window of words from the pre-processed, pre-tokenized context

            Returns:
                query dict
        """
        leftwords=context["left"][-params["wleft"]:]
        rightwords=context["right"][:params["wright"]]
        left_start=params["match_start"]-sum([len(context["left"][-x])+1 for x in range(min(len(context["left"]),params["wleft"]))])
        right_end=params["match_end"]+sum([len(context["right"][x])+1 for x in range(min(len(context["right"]),params["wright"]))])
        extract_dict={
            "left_start":left_start,
            "right_end":right_end,
            "params":(params["wleft"],params["wright"])
            }
        extracted_query=self.joinCitationContext(leftwords,rightwords,extract_dict)
        return extracted_query

    def extract(self, params):
        """
            For window-of-words it's a lot faster to only generate the context
            once and extract the different window sizes from it, so this
            function just returns the same as extractMulti
        """
        return self.extractMulti(params)

    def extractMulti(self, params):
        """
            Default method, up to x words left, x words right
            returns a dict {"left_start","right_end"}
        """
##match, doctext, parameters=[(20,20)], options={"jump_paragraphs":True}
        context_params={
            "wleft":max([x[0] for x in params["parameters"]]),
            "wright":max([x[1] for x in params["parameters"]]),
            "match_start": params["match_start"],
            "match_end": params["match_end"],
            "doctext": params["doctext"],
            }
        context=self.tokenizeContext(context_params)

        res=[]

        for parameter in params["parameters"]:
            params["wleft"]=parameter[0]
            params["wright"]=parameter[1]
            params["current_parameter"]=parameter

            extracted_query=self.selectTokensFromContext(context, params)
            extracted_query["query_method_id"]=self.methodName(params)
            extracted_query["structured_query"]=self.generateStructuredQuery(extracted_query["text"])
            res.append(extracted_query)
        return res

class SentenceQueryExtractor(BaseQueryExtractor):
    """
        Basic sentence extractor,
    """

    def __init__(self):
        pass

    def extract(self, params):
        """
            Returns a StructuredQuery from a selection of

            Args (in params dict):
                docfrom: SciDoc
                cit: citation dict
                selection: one of: ["paragraph", "1up", "1only", "1up_1down"]
                separate_by_tag: "az" or none
                dict_key: which key in the dict leads to the text
        """
        to_add=selectSentencesToAdd(params["docfrom"], params["cit"], params["current_parameter"])

        if params["separate_by_tag"]=="az":
            extracted_query={"ilc_AZ_"+zone:"" for zone in AZ_ZONES_LIST}
        elif params["separate_by_tag"]=="csc":
            extracted_query={"ilc_CSC_"+zone:"" for zone in CORESC_LIST}
        else:
            extracted_query={params["dict_key"]:""}

        for sent_id in to_add:
            sent=params["docfrom"].element_by_id[sent_id]
            text=formatSentenceForIndexing(sent)
            if params.get("separate_by_tag","")=="az":
                extracted_query["ilc_AZ_"+sent["az"]]+=text+" "
            elif params.get("separate_by_tag","")=="csc":
                extracted_query["ilc_CSC_"+sent["csc_type"]]+=text+" "
            else:
                extracted_query[params["dict_key"]]+=text+" "

        extracted_query["params"]=params["current_parameter"]
        extracted_query["query_method_id"]=self.methodName(params)
        extracted_query["structured_query"]=self.generateStructuredQuery(extracted_query["text"])
        return extracted_query

    def extractMulti(self, params):
        """
            Returns one or more sentences put into a same bag of words, separated by

            Args:
                docfrom: SciDoc
                cit: citation dict
                param: one of: ["paragraph", "1up", "1only", "1up_1down"]
                separate_by_tag: "az" or none
                dict_key: which key in the dict leads to the text
        """
##        docfrom, cit, params, separate_by_tag=None, dict_key="text"
        res=[]
        for parameter in params["parameters"]:
            params["current_parameter"]=parameter
            res.append(self.extract(params))
        return res

class SelectedSentenceQueryExtractor(SentenceQueryExtractor):
    """
        class comment
    """

    def __init__(self):
        pass


    def extract(self, params):
        """
            Returns a context as annotated: list of tokens

            From athar_corpus

            Args:

        """
##        docfrom, cit, to_include={"p","n","o"}, to_exclude={"x"}, dict_key="text"
        to_exclude={"x"}
        to_add=selectSentencesToAdd(params["docfrom"], params["cit"], "4up_4down_crosspara")
        to_include=params["current_parameter"]
        if not isinstance(to_include,set):
            to_include=set(to_include)

        extracted_query={}
        extracted_query["text"]=""
        for sent_id in to_add:
            sent=params["docfrom"].element_by_id[sent_id]
            feel=sent["sentiment"]
            if feel:
                feel=set([c for c in sent["sentiment"]])
            else:
                feel=set()

            intersection=(to_include & feel)

            if len(intersection) > 0 and len(to_exclude & feel) == 0:
                # TODO remove names of authors from text
                text=formatSentenceForIndexing(sent)
                if params.get("separate_by_tag","")=="sentiment":
                    extracted_query[unicode(intersection)]+=text+" "
                else:
                    extracted_query[params["dict_key"]]+=text+" "

        extracted_query["params"]=params["current_parameter"]
        extracted_query["query_method_id"]=self.methodName(params)
        extracted_query["structured_query"]=self.generateStructuredQuery(extracted_query["text"])
        return extracted_query

class HeuristicsQueryExtractor(WindowQueryExtractor):
    """
        class comment
    """

    def __init__(self):
        pass

    def extract(self, match, doctext, wleft=40, wright=40, stopbr=False):
        """
            Heuristic extraction of words around citation, dealing with paragraph
            breaks, sentence breaks, etc.
        """
        def modTextExtractContext(text):
            """
                Change linke breaks, paragraph breaks and citations to tokens
            """
            text=re.sub(r"<cit\sid=.{1,5}\s*?/>"," "+CIT_MARKER+" ",text, 0, re.IGNORECASE|re.DOTALL)
            text=re.sub(r"</?footnote.{0,11}>"," ",text, 0, re.IGNORECASE|re.DOTALL)
            text=re.sub(r"\n\n"," "+PAR_MARKER+" ",text)
            text=re.sub(r"\n"," "+BR_MARKER+" ",text)
            return text

        left=doctext[max(0,match.start()-(wleft*ESTIMATED_AVERAGE_WORD_LENGTH)):match.start()] # tokenize!
        left=modTextExtractContext(left)
        left=tokenizeText(left)

        right=doctext[match.end():match.end()+(wright*ESTIMATED_AVERAGE_WORD_LENGTH)] # tokenize!
        right=modTextExtractContext(right)
        right=tokenizeText(right)

        leftwords=[]
        left=[x for x in reversed(left)]
        for w in left[:wleft]:
            new=[]
            if w==PAR_MARKER:    # paragraph break
                break
            if w==CIT_MARKER:    # citation
                break
            if w==BR_MARKER:    # line break
                if stopbr:
                    print("break: br")
                    break
                else:
                    continue
            else:
                new.append(w)
                new.extend(leftwords)
                leftwords=new

        rightwords=[]
        for w in right[:wright]:
            if w==PAR_MARKER:    # paragraph break
                print("break: paragraph")
                break
            if w==CIT_MARKER:    # citation
                print("break: citation")
                break
            if w==BR_MARKER:    # line break
                if stopbr:
                    print("break: br")
                    break
                else:
                    continue
            else:
                rightwords.append(w)

    ##    print "Q Fancy:",
        return self.joinCitationContext(leftwords, rightwords, {})


    def extractMulti(match, doctext, parameters=[(20,20)], maxwords=20, options={"jump_paragraphs":True}):
        """
            Fancier method

            returns a list = [[BOW from param1], [BOW from param2]...]
        """

        left=doctext[max(0,match.start()-(maxwords*ESTIMATED_AVERAGE_WORD_LENGTH)):match.start()] # tokenize!
        left=tokenizeText(removeCitations(left))

        right=doctext[match.end():match.end()+(maxwords*ESTIMATED_AVERAGE_WORD_LENGTH)] # tokenize!
        right=tokenizeText(removeCitations(right))

        res=[]

        for words in parameters:
            leftwords=left[-words[0]:]
            rightwords=right[:words[1]]
            res.append(self.joinCitationContext(leftwords,rightwords))

        return res


EXTRACTOR_LIST={
    "Window":WindowQueryExtractor(),
    "Sentences":SentenceQueryExtractor(),
    "SelectedSentences":SelectedSentenceQueryExtractor(),
    "Heuristics":HeuristicsQueryExtractor(),
    }

def main():

    pass

if __name__ == '__main__':
    main()