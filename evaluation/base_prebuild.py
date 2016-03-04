# <purpose>
#
# Copyright:   (c) Daniel Duma 2015
# Author: Daniel Duma <danielduma@gmail.com>

# For license information, see LICENSE.TXT

from __future__ import print_function
import sys

from prebuild_functions import prebuildMulti
from minerva.squad.tasks import prebuildBOWTask

import minerva.db.corpora as cp
from minerva.proc.results_logging import ProgressIndicator

class BasePrebuilder(object):
    """
        Wrapper around the prebuilding functions.
    """
    def __init__(self, use_celery=False):
        """
        """
        self.use_celery=use_celery
        self.exp={}
        self.options={}

    def prebuildBOWsForTests(self, exp, options):
        """
            Generates BOWs for each document from its inlinks, stores them in a
            corpus cached file

            :param parameters: list of parameters
            :param maxfiles: max. number of files to process. Simple parameter for debug
            :param force_prebuild: should BOWs be rebuilt even if existing?

        """
        self.exp=exp
        self.options=options

        maxfiles=options.get("max_files_to_process",sys.maxint)

        if len(self.exp.get("rhetorical_annotations",[])) > 0:
            print("Loading AZ/CFC classifiers")
            cp.Corpus.loadAnnotators()

        print("Prebuilding BOWs for", min(len(cp.Corpus.ALL_FILES),maxfiles), "files...")
        numfiles=min(len(cp.Corpus.ALL_FILES),maxfiles)

        if self.use_celery:
            print("Queueing tasks...")
            tasks=[]
            for guid in cp.Corpus.ALL_FILES[:maxfiles]:
                for method_name in self.exp["prebuild_bows"]:
                    run_annotators=self.exp.get("rhetorical_annotations",[]) if self.exp.get("run_rhetorical_annotators",False) else []
                    if self.use_celery:
                        tasks.append(prebuildBOWTask.apply_async(args=[
                            method_name,
                            self.exp["prebuild_bows"][method_name]["parameters"],
                            self.exp["prebuild_bows"][method_name]["function_name"],
                            guid,
                            self.options["force_prebuild"],
                            run_annotators],
                            queue="prebuild_bows"))

        else:
            progress=ProgressIndicator(True, numfiles, False)
            for guid in cp.Corpus.ALL_FILES[:maxfiles]:
                for method_name in self.exp["prebuild_bows"]:
                    run_annotators=self.exp.get("rhetorical_annotations",[]) if self.exp.get("run_rhetorical_annotators",False) else []
                    prebuildMulti(
                                  method_name,
                                  self.exp["prebuild_bows"][method_name]["parameters"],
                                  self.exp["prebuild_bows"][method_name]["function"],
                                  None,
                                  None,
                                  guid,
                                  self.options["force_prebuild"],
                                  run_annotators
                                  )
                progress.showProgressReport("Building BOWs")


def main():
    pass

if __name__ == '__main__':
    main()
