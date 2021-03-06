# -*- coding: utf8 -*-

import json
import re
import string

import numpy as np

from utils.datasets import Datasets
from utils.es_manager import ES_Manager


MAX_POSITIVE_SAMPLE_SIZE = 10000



def get_fields(es_m):
    """ Crete field list from fields in the Elasticsearch mapping
    """
    fields = []
    mapped_fields = es_m.get_mapped_fields()

    for data in mapped_fields:
        path = data['path']
        path_list = path.split('.')
        label = '{0} --> {1}'.format(path_list[0], ' --> '.join(path_list[1:])) if len(path_list) > 1 else path_list[0]
        label = label.replace('-->', u'→')
        field = {'data': json.dumps(data), 'label': label}
        fields.append(field)

    # Sort fields by label
    fields = sorted(fields, key=lambda l: l['label'])

    return fields


class esIteratorError(Exception):
    """ esIterator Exception
    """
    pass


class Lexicon:

    def __init__(self, reduction_methods):
        self.punct_re = re.compile('[%s]' % re.escape(string.punctuation))
        self.reduction_methods = reduction_methods

    def lexicon_reduction(self, doc_text):
        sentences = doc_text.split('\n')
        if u'remove_numbers' in self.reduction_methods:
            sentences = [re.sub('(\d)+', 'n', sentence) for sentence in sentences]
        if u'remove_punctuation' in self.reduction_methods:
            sentences = [self.punct_re.sub('[punct]', sentence) for sentence in sentences]
        doc_text = ' '.join(sentences)
        return doc_text


class EsDataSample(object):

    def __init__(self, query, field, request):
        self.field = field
        self.request = request
        reduction_methods = self.request.POST.getlist('lexicon_reduction[]')
        self.lexicon = Lexicon(reduction_methods)
        # Define selected mapping
        ds = Datasets().activate_dataset(request.session)
        self.es_m = ds.build_manager(ES_Manager)
        self.es_m.load_combined_query(query)

    def _get_positive_samples(self, sample_size):
        positive_samples = []
        positive_set = set()

        self.es_m.set_query_parameter('size', 100)
        response = self.es_m.scroll()
        scroll_id = response['_scroll_id']
        l = response['hits']['total']
        while l > 0 and len(positive_samples) <= sample_size:

            response = self.es_m.scroll(scroll_id=scroll_id)
            l = len(response['hits']['hits'])
            scroll_id = response['_scroll_id']

            # Check errors in the database request
            if (response['_shards']['total'] > 0 and response['_shards']['successful'] == 0) or response['timed_out']:
                msg = 'Elasticsearch failed to retrieve documents: ' \
                      '*** Shards: {0} *** Timeout: {1} *** Took: {2}'.format(response['_shards'],
                                                                              response['timed_out'], response['took'])
                raise esIteratorError(msg)

            for hit in response['hits']['hits']:
                try:
                    # Take into account nested fields encoded as: 'field.sub_field'
                    decoded_text = hit['_source']
                    for k in self.field.split('.'):
                        decoded_text = decoded_text[k]
                    doc_text = self.lexicon.lexicon_reduction(decoded_text)
                    doc_id = str(hit['_id'])
                    positive_samples.append(doc_text)
                    positive_set.add(doc_id)
                except KeyError as e:
                    # If the field is missing from the document
                    pass

        return positive_samples, positive_set

    def _get_negative_samples(self, positive_set):
        negative_samples = []
        response = self.es_m.scroll_all_match()
        scroll_id = response['_scroll_id']
        l = response['hits']['total']
        sample_size = len(positive_set)

        while l > 0 and len(negative_samples) <= sample_size:

            response = self.es_m.scroll_all_match(scroll_id=scroll_id)
            l = len(response['hits']['hits'])
            scroll_id = response['_scroll_id']

            # Check errors in the database request
            if (response['_shards']['total'] > 0 and response['_shards']['successful'] == 0) or response['timed_out']:
                msg = 'Elasticsearch failed to retrieve documents: ' \
                      '*** Shards: {0} *** Timeout: {1} *** Took: {2}'.format(response['_shards'],
                                                                              response['timed_out'], response['took'])
                raise esIteratorError(msg)

            for hit in response['hits']['hits']:
                try:
                    doc_id = str(hit['_id'])
                    if doc_id in positive_set:
                        continue
                    # Take into account nested fields encoded as: 'field.sub_field'
                    decoded_text = hit['_source']
                    for k in self.field.split('.'):
                        decoded_text = decoded_text[k]
                    doc_text = self.lexicon.lexicon_reduction(decoded_text)
                    negative_samples.append(doc_text)
                except KeyError as e:
                    # If the field is missing from the document
                    pass

        return negative_samples

    def get_data_samples(self, sample_size=MAX_POSITIVE_SAMPLE_SIZE):
        positive_samples, positive_set = self._get_positive_samples(sample_size)
        negative_samples = self._get_negative_samples(positive_set)
        data_sample_x = np.asarray(positive_samples + negative_samples)
        data_sample_y = np.asarray([1] * len(positive_samples) + [0] * len(negative_samples))

        statistics = {}
        statistics['total_positive'] = len(positive_samples)
        statistics['total_negative'] = len(negative_samples)
        return data_sample_x, data_sample_y, statistics


class EsDataClassification(object):

    def __init__(self, es_index, es_mapping, field, query):
        # Dataset info
        self.es_index = es_index
        self.es_mapping = es_mapping
        self.field = field
        # Build ES manager
        self.es_m = ES_Manager(es_index, es_mapping)
        self.es_m.load_combined_query(query)

    def get_total_documents(self):
        return self.es_m.get_total_documents()

    def get_tags_by_id(self, doc_id):
        request_url = '{0}/{1}/{2}/{3}'.format(self.es_m.es_url, self.es_index, self.es_mapping, doc_id)
        response = ES_Manager.plain_get(request_url)
        doc = []
        try:
            doc = response['_source']['texta_link']['tags']
        except KeyError:
            pass
        return doc

    def apply_classifier(self, clf_model, model_tag):

        response = self.es_m.scroll()
        scroll_id = response['_scroll_id']
        l = response['hits']['total']
        total_processed = 0
        positive_docs = []

        # Get all positive documents
        while l > 0:

            # Check errors in the database request
            if (response['_shards']['total'] > 0 and response['_shards']['successful'] == 0) or response['timed_out']:
                msg = 'Elasticsearch failed to retrieve documents: ' \
                      '*** Shards: {0} *** Timeout: {1} *** Took: {2}'.format(response['_shards'],
                                                                              response['timed_out'], response['took'])
                raise esIteratorError(msg)

            for hit in response['hits']['hits']:
                try:
                    total_processed += 1
                    doc_id = str(hit['_id'])
                    # Take into account nested fields encoded as: 'field.sub_field'
                    decoded_text = hit['_source']
                    for k in self.field.split('.'):
                        decoded_text = decoded_text[k]
                    pred = clf_model.predict([decoded_text])[0]

                    if pred == 1:
                        positive_docs.append(doc_id)
                except KeyError as e:
                    # If the field is missing from the document
                    pass

            # New scroll request
            response = self.es_m.scroll(scroll_id=scroll_id)
            l = len(response['hits']['hits'])
            scroll_id = response['_scroll_id']

        # Apply update to positive documents
        for doc_id in positive_docs:
            doc_tags = self.get_tags_by_id(doc_id)
            # Check if document has tag already
            if model_tag not in doc_tags:
                doc_tags.append(model_tag)
            base_url = '{0}/{1}/{2}/{3}/_update'
            request_url = base_url.format(self.es_m.es_url, self.es_index, self.es_mapping, doc_id)
            texta_tags = {'texta_link': {'tags': doc_tags}}
            d = json.dumps({'doc': texta_tags})
            response = self.es_m.plain_post(request_url, d)

        total_positive = len(positive_docs)
        data = {}
        data['total_processed'] = total_processed
        data['total_positive'] = total_positive
        data['total_negative'] = total_processed - total_positive
        data['total_documents'] = self.get_total_documents()
        return data
