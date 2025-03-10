# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

from collections import defaultdict
import os
import pytest
import platform
import functools
import itertools
import datetime
import json
from unittest import mock
from azure.core.exceptions import HttpResponseError, ClientAuthenticationError
from azure.core.credentials import AzureKeyCredential
from testcase import TextAnalyticsTest, TextAnalyticsPreparer, is_public_cloud
from testcase import TextAnalyticsClientPreparer as _TextAnalyticsClientPreparer
from devtools_testutils import recorded_by_proxy, set_custom_default_matcher
from azure.ai.textanalytics import (
    TextAnalyticsClient,
    RecognizeEntitiesAction,
    RecognizeLinkedEntitiesAction,
    RecognizePiiEntitiesAction,
    ExtractKeyPhrasesAction,
    AnalyzeSentimentAction,
    TextDocumentInput,
    VERSION,
    TextAnalyticsApiVersion,
    _AnalyzeActionsType,
    ExtractKeyPhrasesResult,
    AnalyzeSentimentResult,
    RecognizeLinkedEntitiesResult,
    RecognizeEntitiesResult,
    RecognizePiiEntitiesResult,
    ExtractSummaryAction,
    PiiEntityCategory,
    ExtractSummaryResult,
    SingleCategoryClassifyAction,
    MultiCategoryClassifyAction,
    RecognizeCustomEntitiesAction,
    SingleCategoryClassifyResult,
    MultiCategoryClassifyResult,
    RecognizeCustomEntitiesResult
)

# pre-apply the client_cls positional argument so it needn't be explicitly passed below
TextAnalyticsClientPreparer = functools.partial(_TextAnalyticsClientPreparer, TextAnalyticsClient)

TextAnalyticsCustomPreparer = functools.partial(
    TextAnalyticsPreparer,
    textanalytics_custom_text_endpoint="https://fakeendpoint.cognitiveservices.azure.com",
    textanalytics_custom_text_key="fakeZmFrZV9hY29jdW50X2tleQ==",
    textanalytics_single_category_classify_project_name="single_category_classify_project_name",
    textanalytics_single_category_classify_deployment_name="single_category_classify_deployment_name",
    textanalytics_multi_category_classify_project_name="multi_category_classify_project_name",
    textanalytics_multi_category_classify_deployment_name="multi_category_classify_deployment_name",
    textanalytics_custom_entities_project_name="custom_entities_project_name",
    textanalytics_custom_entities_deployment_name="custom_entities_deployment_name",
)

class TestAnalyze(TextAnalyticsTest):

    def _interval(self):
        return 5 if self.is_live else 0

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_no_single_input(self, client):
        with pytest.raises(TypeError):
            response = client.begin_analyze_actions("hello world", actions=[], polling_interval=self._interval())

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_all_successful_passing_dict_key_phrase_task(self, client):
        docs = [{"id": "1", "language": "en", "text": "Microsoft was founded by Bill Gates and Paul Allen"},
                {"id": "2", "language": "es", "text": "Microsoft fue fundado por Bill Gates y Paul Allen"}]

        response = client.begin_analyze_actions(
            docs,
            actions=[ExtractKeyPhrasesAction()],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        document_results = list(response)

        assert len(document_results) == 2
        for document_result in document_results:
            assert len(document_result) == 1
            for document_result in document_result:
                assert isinstance(document_result, ExtractKeyPhrasesResult)
                assert "Paul Allen" in document_result.key_phrases
                assert "Bill Gates" in document_result.key_phrases
                assert "Microsoft" in document_result.key_phrases
                assert document_result.id is not None

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_all_successful_passing_dict_sentiment_task(self, client):
        docs = [{"id": "1", "language": "en", "text": "Microsoft was founded by Bill Gates and Paul Allen."},
                {"id": "2", "language": "en", "text": "I did not like the hotel we stayed at. It was too expensive."},
                {"id": "3", "language": "en", "text": "The restaurant had really good food. I recommend you try it."}]

        response = client.begin_analyze_actions(
            docs,
            actions=[AnalyzeSentimentAction()],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        pages = list(response)

        assert len(pages) == len(docs)
        for idx, document_results in enumerate(pages):
            assert len(document_results) == 1
            document_result = document_results[0]
            assert isinstance(document_result, AnalyzeSentimentResult)
            assert document_result.id is not None
            assert document_result.statistics is not None
            self.validateConfidenceScores(document_result.confidence_scores)
            assert document_result.sentences is not None
            if idx == 0:
                assert document_result.sentiment == "neutral"
                assert len(document_result.sentences) == 1
                assert document_result.sentences[0].text == "Microsoft was founded by Bill Gates and Paul Allen."
            elif idx == 1:
                assert document_result.sentiment == "negative"
                assert len(document_result.sentences) == 2
                assert document_result.sentences[0].text == "I did not like the hotel we stayed at."
                assert document_result.sentences[1].text == "It was too expensive."
            else:
                assert document_result.sentiment == "positive"
                assert len(document_result.sentences) == 2
                assert document_result.sentences[0].text == "The restaurant had really good food."
                assert document_result.sentences[1].text == "I recommend you try it."

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_sentiment_analysis_task_with_opinion_mining(self, client):
        documents = [
            "It has a sleek premium aluminum design that makes it beautiful to look at.",
            "The food and service is not good"
        ]

        response = client.begin_analyze_actions(
            documents,
            actions=[AnalyzeSentimentAction(show_opinion_mining=True)],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        pages = list(response)

        assert len(pages) == len(documents)
        for idx, document_results in enumerate(pages):
            assert len(document_results) == 1
            document_result = document_results[0]
            assert isinstance(document_result, AnalyzeSentimentResult)
            for sentence in document_result.sentences:
                if idx == 0:
                    for mined_opinion in sentence.mined_opinions:
                        target = mined_opinion.target
                        assert 'design' == target.text
                        assert 'positive' == target.sentiment
                        assert 0.0 == target.confidence_scores.neutral
                        self.validateConfidenceScores(target.confidence_scores)
                        assert 32 == target.offset

                        sleek_opinion = mined_opinion.assessments[0]
                        assert 'sleek' == sleek_opinion.text
                        assert 'positive' == sleek_opinion.sentiment
                        assert 0.0 == sleek_opinion.confidence_scores.neutral
                        self.validateConfidenceScores(sleek_opinion.confidence_scores)
                        assert 9 == sleek_opinion.offset
                        assert not sleek_opinion.is_negated

                        premium_opinion = mined_opinion.assessments[1]
                        assert 'premium' == premium_opinion.text
                        assert 'positive' == premium_opinion.sentiment
                        assert 0.0 == premium_opinion.confidence_scores.neutral
                        self.validateConfidenceScores(premium_opinion.confidence_scores)
                        assert 15 == premium_opinion.offset
                        assert not premium_opinion.is_negated
                else:
                    food_target = sentence.mined_opinions[0].target
                    service_target = sentence.mined_opinions[1].target
                    self.validateConfidenceScores(food_target.confidence_scores)
                    assert 4 == food_target.offset

                    assert 'service' == service_target.text
                    assert 'negative' == service_target.sentiment
                    assert 0.0 == service_target.confidence_scores.neutral
                    self.validateConfidenceScores(service_target.confidence_scores)
                    assert 13 == service_target.offset

                    food_opinion = sentence.mined_opinions[0].assessments[0]
                    service_opinion = sentence.mined_opinions[1].assessments[0]
                    self.assertOpinionsEqual(food_opinion, service_opinion)

                    assert 'good' == food_opinion.text
                    assert 'negative' == food_opinion.sentiment
                    assert 0.0 == food_opinion.confidence_scores.neutral
                    self.validateConfidenceScores(food_opinion.confidence_scores)
                    assert 28 == food_opinion.offset
                    assert food_opinion.is_negated
                    service_target = sentence.mined_opinions[1].target

                    assert 'food' == food_target.text
                    assert 'negative' == food_target.sentiment
                    assert 0.0 == food_target.confidence_scores.neutral

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_all_successful_passing_text_document_input_entities_task(self, client):
        docs = [
            TextDocumentInput(id="1", text="Microsoft was founded by Bill Gates and Paul Allen on April 4, 1975", language="en"),
            TextDocumentInput(id="2", text="Microsoft fue fundado por Bill Gates y Paul Allen el 4 de abril de 1975.", language="es"),
            TextDocumentInput(id="3", text="Microsoft wurde am 4. April 1975 von Bill Gates und Paul Allen gegründet.", language="de"),
        ]

        response = client.begin_analyze_actions(
            docs,
            actions=[RecognizeEntitiesAction()],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        pages = list(response)
        assert len(pages) == len(docs)

        for document_results in pages:
            assert len(document_results) == 1
            document_result = document_results[0]
            assert isinstance(document_result, RecognizeEntitiesResult)
            assert len(document_result.entities) == 4
            assert document_result.id is not None
            for entity in document_result.entities:
                assert entity.text is not None
                assert entity.category is not None
                assert entity.offset is not None
                assert entity.confidence_score is not None
                assert entity.category is not None
                assert entity.offset is not None
                assert entity.confidence_score is not None

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_all_successful_passing_string_pii_entities_task(self, client):

        docs = ["My SSN is 859-98-0987.",
                "Your ABA number - 111000025 - is the first 9 digits in the lower left hand corner of your personal check.",
                "Is 998.214.865-68 your Brazilian CPF number?"
        ]

        response = client.begin_analyze_actions(
            docs,
            actions=[RecognizePiiEntitiesAction()],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        pages = list(response)
        assert len(pages) == len(docs)

        for idx, document_results in enumerate(pages):
            assert len(document_results) == 1
            document_result = document_results[0]
            assert isinstance(document_result, RecognizePiiEntitiesResult)
            if idx == 0:
                assert document_result.entities[0].text == "859-98-0987"
                assert document_result.entities[0].category == "USSocialSecurityNumber"
            elif idx == 1:
                assert document_result.entities[0].text == "111000025"
            for entity in document_result.entities:
                assert entity.text is not None
                assert entity.category is not None
                assert entity.offset is not None
                assert entity.confidence_score is not None

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_bad_request_on_empty_document(self, client):
        docs = [""]

        with pytest.raises(HttpResponseError):
            response = client.begin_analyze_actions(
                docs,
                actions=[ExtractKeyPhrasesAction()],
                polling_interval=self._interval(),
            )

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer(client_kwargs={
        "textanalytics_test_api_key": "",
    })
    @recorded_by_proxy
    def test_empty_credential_class(self, client):
        with pytest.raises(ClientAuthenticationError):
            response = client.begin_analyze_actions(
                ["This is written in English."],
                actions=[
                    RecognizeEntitiesAction(),
                    ExtractKeyPhrasesAction(),
                    RecognizePiiEntitiesAction(),
                    RecognizeLinkedEntitiesAction(),
                    AnalyzeSentimentAction(),
                    ExtractSummaryAction()
                ],
                polling_interval=self._interval(),
            )

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer(client_kwargs={
        "textanalytics_test_api_key": "xxxxxxxxxxxx",
    })
    @recorded_by_proxy
    def test_bad_credentials(self, client):
        with pytest.raises(ClientAuthenticationError):
            response = client.begin_analyze_actions(
                ["This is written in English."],
                actions=[
                    RecognizeEntitiesAction(),
                    ExtractKeyPhrasesAction(),
                    RecognizePiiEntitiesAction(),
                    RecognizeLinkedEntitiesAction(),
                    AnalyzeSentimentAction(),
                    ExtractSummaryAction()
                ],
                polling_interval=self._interval(),
            )

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_out_of_order_ids_multiple_tasks(self, client):
        docs = [{"id": "56", "text": ":)"},
                {"id": "0", "text": ":("},
                {"id": "19", "text": ":P"},
                {"id": "1", "text": ":D"}]

        response = client.begin_analyze_actions(
            docs,
            actions=[
                RecognizeEntitiesAction(),
                ExtractKeyPhrasesAction(),
                RecognizePiiEntitiesAction(),
                RecognizeLinkedEntitiesAction(),
                AnalyzeSentimentAction(),
                ExtractSummaryAction()
            ],
            polling_interval=self._interval(),
        ).result()

        results = list(response)
        assert len(results) == len(docs)

        document_order = ["56", "0", "19", "1"]
        action_order = [
            _AnalyzeActionsType.RECOGNIZE_ENTITIES,
            _AnalyzeActionsType.EXTRACT_KEY_PHRASES,
            _AnalyzeActionsType.RECOGNIZE_PII_ENTITIES,
            _AnalyzeActionsType.RECOGNIZE_LINKED_ENTITIES,
            _AnalyzeActionsType.ANALYZE_SENTIMENT,
            _AnalyzeActionsType.EXTRACT_SUMMARY
        ]
        for doc_idx, document_results in enumerate(results):
            assert len(document_results) == 6
            for action_idx, document_result in enumerate(document_results):
                assert document_result.id == document_order[doc_idx]
                assert self.document_result_to_action_type(document_result) == action_order[action_idx]

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_show_stats_and_model_version_multiple_tasks(self, client):

        def callback(resp):
            assert resp.raw_response
            tasks = resp.raw_response['tasks']
            assert tasks['completed'] == 6
            assert tasks['inProgress'] == 0
            assert tasks['failed'] == 0
            assert tasks['total'] == 6
            num_tasks = 0
            for key, task in tasks.items():
                if "Tasks" in key:
                    num_tasks += 1
                    assert len(task) == 1
                    task_stats = task[0]['results']['statistics']
                    assert task_stats['documentsCount'] == 4
                    assert task_stats['validDocumentsCount'] == 4
                    assert task_stats['erroneousDocumentsCount'] == 0
                    assert task_stats['transactionsCount'] == 4
            assert num_tasks == 6

        docs = [{"id": "56", "text": ":)"},
                {"id": "0", "text": ":("},
                {"id": "19", "text": ":P"},
                {"id": "1", "text": ":D"}]

        poller = client.begin_analyze_actions(
            docs,
            actions=[
                RecognizeEntitiesAction(model_version="latest"),
                ExtractKeyPhrasesAction(model_version="latest"),
                RecognizePiiEntitiesAction(model_version="latest"),
                RecognizeLinkedEntitiesAction(model_version="latest"),
                AnalyzeSentimentAction(model_version="latest"),
                ExtractSummaryAction(model_version="latest")
            ],
            show_stats=True,
            polling_interval=self._interval(),
            raw_response_hook=callback,
        )

        response = poller.result()

        pages = list(response)
        assert len(pages) == len(docs)
        action_order = [
            _AnalyzeActionsType.RECOGNIZE_ENTITIES,
            _AnalyzeActionsType.EXTRACT_KEY_PHRASES,
            _AnalyzeActionsType.RECOGNIZE_PII_ENTITIES,
            _AnalyzeActionsType.RECOGNIZE_LINKED_ENTITIES,
            _AnalyzeActionsType.ANALYZE_SENTIMENT,
            _AnalyzeActionsType.EXTRACT_SUMMARY
        ]
        for document_results in pages:
            assert len(document_results) == len(action_order)
            for document_result in document_results:
                assert document_result.statistics
                assert document_result.statistics.character_count
                assert document_result.statistics.transaction_count

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_poller_metadata(self, client):
        docs = [{"id": "56", "text": ":)"}]

        poller = client.begin_analyze_actions(
            docs,
            actions=[
                RecognizeEntitiesAction(model_version="latest")
            ],
            show_stats=True,
            polling_interval=self._interval(),
        )

        poller.result()

        assert isinstance(poller.created_on, datetime.datetime)
        assert not poller.display_name
        assert isinstance(poller.expires_on, datetime.datetime)
        assert poller.actions_failed_count == 0
        assert poller.actions_in_progress_count == 0
        assert poller.actions_succeeded_count == 1
        assert isinstance(poller.last_modified_on, datetime.datetime)
        assert poller.total_actions_count == 1
        assert poller.id

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_invalid_language_hint_method(self, client):
        response = list(client.begin_analyze_actions(
            ["This should fail because we're passing in an invalid language hint"],
            language="notalanguage",
            actions=[
                RecognizeEntitiesAction(),
                ExtractKeyPhrasesAction(),
                RecognizePiiEntitiesAction(),
                RecognizeLinkedEntitiesAction(),
                AnalyzeSentimentAction(),
                ExtractSummaryAction()
            ],
            polling_interval=self._interval(),
        ).result())

        for document_results in response:
            for doc in document_results:
                assert doc.is_error

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_bad_model_version_error_multiple_tasks(self, client):
        docs = [{"id": "1", "language": "english", "text": "I did not like the hotel we stayed at."}]

        with pytest.raises(HttpResponseError):
            client.begin_analyze_actions(
                docs,
                actions=[
                    RecognizeEntitiesAction(model_version="latest"),
                    ExtractKeyPhrasesAction(model_version="bad"),
                    RecognizePiiEntitiesAction(model_version="bad"),
                    RecognizeLinkedEntitiesAction(model_version="bad"),
                    AnalyzeSentimentAction(model_version="bad"),
                    ExtractSummaryAction(model_version="bad")
                ],
                polling_interval=self._interval(),
            ).result()

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_bad_model_version_error_all_tasks(self, client):  # TODO: verify behavior of service
        docs = [{"id": "1", "language": "english", "text": "I did not like the hotel we stayed at."}]

        with pytest.raises(HttpResponseError):
            client.begin_analyze_actions(
                docs,
                actions=[
                    RecognizeEntitiesAction(model_version="bad"),
                    ExtractKeyPhrasesAction(model_version="bad"),
                    RecognizePiiEntitiesAction(model_version="bad"),
                    RecognizeLinkedEntitiesAction(model_version="bad"),
                    AnalyzeSentimentAction(model_version="bad"),
                    ExtractSummaryAction(model_version="bad")
                ],
                polling_interval=self._interval(),
            ).result()

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_missing_input_records_error(self, client):
        docs = []
        with pytest.raises(ValueError) as excinfo:
            client.begin_analyze_actions(
                docs,
                actions=[
                    RecognizeEntitiesAction(),
                    ExtractKeyPhrasesAction(),
                    RecognizePiiEntitiesAction(),
                    RecognizeLinkedEntitiesAction(),
                    AnalyzeSentimentAction(),
                    ExtractSummaryAction()
                ],
                polling_interval=self._interval(),
            )
        assert "Input documents can not be empty or None" in str(excinfo.value)

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_passing_none_docs(self, client):
        with pytest.raises(ValueError) as excinfo:
            client.begin_analyze_actions(None, None)
        assert "Input documents can not be empty or None" in str(excinfo.value)

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_pass_cls(self, client):
        def callback(pipeline_response, deserialized, _):
            return "cls result"
        res = client.begin_analyze_actions(
            documents=["Test passing cls to endpoint"],
            actions=[
                RecognizeEntitiesAction(),
            ],
            cls=callback,
            polling_interval=self._interval(),
        ).result()
        assert res == "cls result"

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_multiple_pages_of_results_returned_successfully(self, client):
        single_doc = "hello world"
        docs = [{"id": str(idx), "text": val} for (idx, val) in enumerate(list(itertools.repeat(single_doc, 25)))] # max number of documents is 25

        result = client.begin_analyze_actions(
            docs,
            actions=[
                RecognizeEntitiesAction(),
                ExtractKeyPhrasesAction(),
                RecognizePiiEntitiesAction(),
                RecognizeLinkedEntitiesAction(),
                AnalyzeSentimentAction(),
                ExtractSummaryAction()
            ],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        pages = list(result)
        assert len(pages) == len(docs)
        action_order = [
            _AnalyzeActionsType.RECOGNIZE_ENTITIES,
            _AnalyzeActionsType.EXTRACT_KEY_PHRASES,
            _AnalyzeActionsType.RECOGNIZE_PII_ENTITIES,
            _AnalyzeActionsType.RECOGNIZE_LINKED_ENTITIES,
            _AnalyzeActionsType.ANALYZE_SENTIMENT,
            _AnalyzeActionsType.EXTRACT_SUMMARY
        ]
        action_type_to_document_results = defaultdict(list)

        for doc_idx, page in enumerate(pages):
            for action_idx, document_result in enumerate(page):
                assert document_result.id == str(doc_idx)
                action_type = self.document_result_to_action_type(document_result)
                assert action_type == action_order[action_idx]
                action_type_to_document_results[action_type].append(document_result)

        assert len(action_type_to_document_results) == len(action_order)
        for document_results in action_type_to_document_results.values():
            assert len(document_results) == len(docs)

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_too_many_documents(self, client):
        docs = list(itertools.repeat("input document", 26))  # Maximum number of documents per request is 25

        with pytest.raises(HttpResponseError) as excinfo:
            client.begin_analyze_actions(
                docs,
                actions=[
                    RecognizeEntitiesAction(),
                    ExtractKeyPhrasesAction(),
                    RecognizePiiEntitiesAction(),
                    RecognizeLinkedEntitiesAction(),
                    AnalyzeSentimentAction(),
                    ExtractSummaryAction()
                ],
                polling_interval=self._interval(),
            )
        assert excinfo.value.status_code == 400

    @pytest.mark.skipif(not is_public_cloud(), reason='Usgov and China Cloud are not supported')
    @TextAnalyticsCustomPreparer()
    @recorded_by_proxy
    def test_disable_service_logs(
            self,
            textanalytics_custom_text_endpoint,
            textanalytics_custom_text_key,
            textanalytics_single_category_classify_project_name,
            textanalytics_single_category_classify_deployment_name,
            textanalytics_multi_category_classify_project_name,
            textanalytics_multi_category_classify_deployment_name,
            textanalytics_custom_entities_project_name,
            textanalytics_custom_entities_deployment_name
    ):
        # this can be reverted to set_bodiless_matcher() after tests are re-recorded and don't contain these headers
        set_custom_default_matcher(
            compare_bodies=False, excluded_headers="Authorization,Content-Length,x-ms-client-request-id,x-ms-request-id"
        )  # don't match on body for this test since we scrub the proj/deployment values
        client = TextAnalyticsClient(textanalytics_custom_text_endpoint, AzureKeyCredential(textanalytics_custom_text_key))
        actions = [
            RecognizeEntitiesAction(disable_service_logs=True),
            ExtractKeyPhrasesAction(disable_service_logs=True),
            RecognizePiiEntitiesAction(disable_service_logs=True),
            RecognizeLinkedEntitiesAction(disable_service_logs=True),
            AnalyzeSentimentAction(disable_service_logs=True),
            ExtractSummaryAction(disable_service_logs=True),
            SingleCategoryClassifyAction(
                project_name=textanalytics_single_category_classify_project_name,
                deployment_name=textanalytics_single_category_classify_deployment_name,
                disable_service_logs=True
            ),
            MultiCategoryClassifyAction(
                project_name=textanalytics_multi_category_classify_project_name,
                deployment_name=textanalytics_multi_category_classify_deployment_name,
                disable_service_logs=True
            ),
            RecognizeCustomEntitiesAction(
                project_name=textanalytics_custom_entities_project_name,
                deployment_name=textanalytics_custom_entities_deployment_name,
                disable_service_logs=True
            )
        ]

        for action in actions:
            assert action.disable_service_logs

        def callback(resp):
            tasks = json.loads(resp.http_request.body)["tasks"]
            assert len(tasks) == len(actions)
            for task in tasks.values():
                assert task[0]["parameters"]["loggingOptOut"]

        client.begin_analyze_actions(
            documents=["Test for logging disable"],
            actions=actions,
            polling_interval=self._interval(),
            raw_response_hook=callback,
        ).result()

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_pii_action_categories_filter(self, client):

        docs = [{"id": "1", "text": "My SSN is 859-98-0987."},
                {"id": "2",
                 "text": "Your ABA number - 111000025 - is the first 9 digits in the lower left hand corner of your personal check."},
                {"id": "3", "text": "Is 998.214.865-68 your Brazilian CPF number?"}]

        actions = [
            RecognizePiiEntitiesAction(
                categories_filter=[
                    PiiEntityCategory.US_SOCIAL_SECURITY_NUMBER,
                    PiiEntityCategory.ABA_ROUTING_NUMBER,
                ]
            ),
        ]

        result = client.begin_analyze_actions(documents=docs, actions=actions, polling_interval=self._interval()).result()
        action_results = list(result)
        assert len(action_results) == 3

        assert action_results[0][0].entities[0].text == "859-98-0987"
        assert action_results[0][0].entities[0].category == PiiEntityCategory.US_SOCIAL_SECURITY_NUMBER
        assert action_results[1][0].entities[0].text == "111000025"
        assert action_results[1][0].entities[0].category == PiiEntityCategory.ABA_ROUTING_NUMBER
        assert action_results[2][0].entities == []  # No Brazilian CPF since not in categories_filter

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_partial_success_for_actions(self, client):
        docs = [{"id": "1", "language": "tr", "text": "I did not like the hotel we stayed at."},
                {"id": "2", "language": "en", "text": "I did not like the hotel we stayed at."}]

        response = client.begin_analyze_actions(
                docs,
                actions=[
                    AnalyzeSentimentAction(),
                    RecognizePiiEntitiesAction(),
                ],
                polling_interval=self._interval(),
            ).result()

        action_results = list(response)
        assert len(action_results) == len(docs)
        action_order = [
            _AnalyzeActionsType.ANALYZE_SENTIMENT,
            _AnalyzeActionsType.RECOGNIZE_PII_ENTITIES,
        ]

        assert len(action_results[0]) == len(action_order)
        assert len(action_results[1]) == len(action_order)

        # first doc
        assert isinstance(action_results[0][0], AnalyzeSentimentResult)
        assert action_results[0][0].id == "1"
        assert action_results[0][1].is_error
        assert action_results[0][1].id == "1"

        # second doc
        assert isinstance(action_results[1][0], AnalyzeSentimentResult)
        assert action_results[1][0].id == "2"
        assert isinstance(action_results[1][1], RecognizePiiEntitiesResult)
        assert action_results[1][1].id == "2"

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_multiple_of_same_action(self, client):
        docs = [
            {"id": "28", "text": "My SSN is 859-98-0987. Here is another sentence."},
            {"id": "3", "text": "Is 998.214.865-68 your Brazilian CPF number? Here is another sentence."},
            {"id": "5", "language": "en", "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
        ]

        actions = [
            AnalyzeSentimentAction(),
            RecognizePiiEntitiesAction(),
            RecognizeEntitiesAction(),
            RecognizeLinkedEntitiesAction(),
            ExtractSummaryAction(order_by="Rank"),
            RecognizePiiEntitiesAction(categories_filter=[PiiEntityCategory.US_SOCIAL_SECURITY_NUMBER]),
            ExtractKeyPhrasesAction(),
            RecognizeEntitiesAction(),
            AnalyzeSentimentAction(show_opinion_mining=True),
            RecognizeLinkedEntitiesAction(),
            ExtractSummaryAction(max_sentence_count=1),
            ExtractKeyPhrasesAction(),
        ]

        response = client.begin_analyze_actions(
            docs,
            actions=actions,
            polling_interval=self._interval(),
        ).result()

        action_results = list(response)
        assert len(action_results) == len(docs)
        assert len(action_results[0]) == len(actions)
        assert len(action_results[1]) == len(actions)
        assert len(action_results[2]) == len(actions)

        for idx, action_result in enumerate(action_results):
            if idx == 0:
                doc_id = "28"
            elif idx == 1:
                doc_id = "3"
            else:
                doc_id = "5"

            assert isinstance(action_result[0], AnalyzeSentimentResult)
            assert not all([sentence.mined_opinions for sentence in action_result[0].sentences])
            assert action_result[0].id == doc_id

            assert isinstance(action_result[1], RecognizePiiEntitiesResult)
            assert action_result[1].id == doc_id

            assert isinstance(action_result[2], RecognizeEntitiesResult)
            assert action_result[2].id == doc_id

            assert isinstance(action_result[3], RecognizeLinkedEntitiesResult)
            assert action_result[3].id == doc_id

            assert isinstance(action_result[4], ExtractSummaryResult)
            previous_score = 1.0
            for sentence in action_result[4].sentences:
                assert sentence.rank_score <= previous_score
                previous_score = sentence.rank_score
            assert action_result[4].id == doc_id

            assert isinstance(action_result[5], RecognizePiiEntitiesResult)
            assert action_result[5].id == doc_id
            if doc_id == "28":
                assert action_result[5].entities
            else:
                assert not action_result[5].entities

            assert isinstance(action_result[6], ExtractKeyPhrasesResult)
            assert action_result[6].id == doc_id

            assert isinstance(action_result[7], RecognizeEntitiesResult)
            assert action_result[7].id == doc_id

            assert isinstance(action_result[8], AnalyzeSentimentResult)
            assert [sentence.mined_opinions for sentence in action_result[0].sentences]
            assert action_result[8].id == doc_id

            assert isinstance(action_result[9], RecognizeLinkedEntitiesResult)
            assert action_result[9].id == doc_id

            assert isinstance(action_result[10], ExtractSummaryResult)
            assert len(action_result[10].sentences) == 1

            assert isinstance(action_result[11], ExtractKeyPhrasesResult)
            assert action_result[11].id == doc_id

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_multiple_of_same_action_with_partial_results(self, client):
        docs = [{"id": "5", "language": "en", "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
                {"id": "2", "text": ""}]

        actions = [
            ExtractSummaryAction(max_sentence_count=3),
            RecognizePiiEntitiesAction(),
            ExtractSummaryAction(max_sentence_count=5)
        ]

        response = client.begin_analyze_actions(
            docs,
            actions=actions,
            polling_interval=self._interval(),
        ).result()

        action_results = list(response)
        assert len(action_results) == len(docs)
        assert len(action_results[0]) == len(actions)
        assert len(action_results[1]) == len(actions)

        # first doc
        assert isinstance(action_results[0][0], ExtractSummaryResult)
        assert action_results[0][0].id == "5"
        assert isinstance(action_results[0][1], RecognizePiiEntitiesResult)
        assert action_results[0][1].id == "5"
        assert isinstance(action_results[0][2], ExtractSummaryResult)
        assert action_results[0][2].id == "5"

        # second doc
        assert action_results[1][0].is_error
        assert action_results[1][1].is_error
        assert action_results[1][2].is_error

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_all_successful_passing_dict_extract_summary_action(self, client):
        docs = [{"id": "1", "language": "en", "text":
            "The government of British Prime Minster Theresa May has been plunged into turmoil with the resignation"
            " of two senior Cabinet ministers in a deep split over her Brexit strategy. The Foreign Secretary Boris "
            "Johnson, quit on Monday, hours after the resignation late on Sunday night of the minister in charge of "
            "Brexit negotiations, David Davis. Their decision to leave the government came three days after May "
            "appeared to have agreed a deal with her fractured Cabinet on the UK's post Brexit relationship with "
            "the EU. That plan is now in tatters and her political future appears uncertain. May appeared in Parliament"
            " on Monday afternoon to defend her plan, minutes after Downing Street confirmed the departure of Johnson. "
            "May acknowledged the splits in her statement to MPs, saying of the ministers who quit: We do not agree "
            "about the best way of delivering our shared commitment to honoring the result of the referendum. The "
            "Prime Minister's latest political drama began late on Sunday night when Davis quit, declaring he could "
            "not support May's Brexit plan. He said it involved too close a relationship with the EU and gave only "
            "an illusion of control being returned to the UK after it left the EU. It seems to me we're giving too "
            "much away, too easily, and that's a dangerous strategy at this time, Davis said in a BBC radio "
            "interview Monday morning. Johnson's resignation came Monday afternoon local time, just before the "
            "Prime Minister was due to make a scheduled statement in Parliament. This afternoon, the Prime Minister "
            "accepted the resignation of Boris Johnson as Foreign Secretary, a statement from Downing Street said."},
            {"id": "2", "language": "es", "text": "Microsoft fue fundado por Bill Gates y Paul Allen"}]

        response = client.begin_analyze_actions(
            docs,
            actions=[ExtractSummaryAction()],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        document_results = list(response)

        assert len(document_results) == 2
        for document_result in document_results:
            assert len(document_result) == 1
            for result in document_result:
                assert isinstance(result, ExtractSummaryResult)
                assert result.statistics
                assert len(result.sentences) == 3 if result.id == 0 else 1
                for sentence in result.sentences:
                    assert sentence.text
                    assert sentence.rank_score is not None
                    assert sentence.offset is not None
                    assert sentence.length is not None
                assert result.id is not None

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_extract_summary_action_with_options(self, client):
        docs = ["The government of British Prime Minster Theresa May has been plunged into turmoil with the resignation"
            " of two senior Cabinet ministers in a deep split over her Brexit strategy. The Foreign Secretary Boris "
            "Johnson, quit on Monday, hours after the resignation late on Sunday night of the minister in charge of "
            "Brexit negotiations, David Davis. Their decision to leave the government came three days after May "
            "appeared to have agreed a deal with her fractured Cabinet on the UK's post Brexit relationship with "
            "the EU. That plan is now in tatters and her political future appears uncertain. May appeared in Parliament"
            " on Monday afternoon to defend her plan, minutes after Downing Street confirmed the departure of Johnson. "
            "May acknowledged the splits in her statement to MPs, saying of the ministers who quit: We do not agree "
            "about the best way of delivering our shared commitment to honoring the result of the referendum. The "
            "Prime Minister's latest political drama began late on Sunday night when Davis quit, declaring he could "
            "not support May's Brexit plan. He said it involved too close a relationship with the EU and gave only "
            "an illusion of control being returned to the UK after it left the EU. It seems to me we're giving too "
            "much away, too easily, and that's a dangerous strategy at this time, Davis said in a BBC radio "
            "interview Monday morning. Johnson's resignation came Monday afternoon local time, just before the "
            "Prime Minister was due to make a scheduled statement in Parliament. This afternoon, the Prime Minister "
            "accepted the resignation of Boris Johnson as Foreign Secretary, a statement from Downing Street said."]

        response = client.begin_analyze_actions(
            docs,
            actions=[ExtractSummaryAction(max_sentence_count=5, order_by="Rank")],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        document_results = list(response)

        assert len(document_results) == 1
        for document_result in document_results:
            assert len(document_result) == 1
            for result in document_result:
                assert isinstance(result, ExtractSummaryResult)
                assert result.statistics
                assert len(result.sentences) == 5
                previous_score = 1.0
                for sentence in result.sentences:
                    assert sentence.rank_score <= previous_score
                    previous_score = sentence.rank_score
                    assert sentence.text
                    assert sentence.offset is not None
                    assert sentence.length is not None
                assert result.id is not None

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_extract_summary_partial_results(self, client):
        docs = [{"id": "1", "language": "en", "text": ""}, {"id": "2", "language": "en", "text": "hello world"}]

        response = client.begin_analyze_actions(
            docs,
            actions=[ExtractSummaryAction()],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        document_results = list(response)
        assert document_results[0][0].is_error
        assert document_results[0][0].error.code == "InvalidDocument"

        assert not document_results[1][0].is_error
        assert isinstance(document_results[1][0], ExtractSummaryResult)

    @pytest.mark.skipif(not is_public_cloud(), reason='Usgov and China Cloud are not supported')
    @TextAnalyticsCustomPreparer()
    @recorded_by_proxy
    def test_single_category_classify(
            self,
            textanalytics_custom_text_endpoint,
            textanalytics_custom_text_key,
            textanalytics_single_category_classify_project_name,
            textanalytics_single_category_classify_deployment_name
    ):
        # this can be reverted to set_bodiless_matcher() after tests are re-recorded and don't contain these headers
        set_custom_default_matcher(
            compare_bodies=False, excluded_headers="Authorization,Content-Length,x-ms-client-request-id,x-ms-request-id"
        )  # don't match on body for this test since we scrub the proj/deployment values
        client = TextAnalyticsClient(textanalytics_custom_text_endpoint, AzureKeyCredential(textanalytics_custom_text_key))
        docs = [
            {"id": "1", "language": "en", "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
            {"id": "2", "language": "en", "text": "David Schmidt, senior vice president--Food Safety, International Food Information Council (IFIC), Washington, D.C., discussed the physical activity component."},
            {"id": "3", "language": "en", "text": "I need a reservation for an indoor restaurant in China. Please don't stop the music. Play music and add it to my playlist"},
        ]

        response = client.begin_analyze_actions(
            docs,
            actions=[
                SingleCategoryClassifyAction(
                    project_name=textanalytics_single_category_classify_project_name,
                    deployment_name=textanalytics_single_category_classify_deployment_name
                )
            ],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        document_results = list(response)
        for doc_result in document_results:
            for result in doc_result:
                assert result.id
                assert not result.is_error
                assert not result.warnings
                assert result.statistics
                assert result.classification.category
                assert result.classification.confidence_score

    @pytest.mark.skipif(not is_public_cloud(), reason='Usgov and China Cloud are not supported')
    @TextAnalyticsCustomPreparer()
    @recorded_by_proxy
    def test_multi_category_classify(
            self,
            textanalytics_custom_text_endpoint,
            textanalytics_custom_text_key,
            textanalytics_multi_category_classify_project_name,
            textanalytics_multi_category_classify_deployment_name
    ):
        # this can be reverted to set_bodiless_matcher() after tests are re-recorded and don't contain these headers
        set_custom_default_matcher(
            compare_bodies=False, excluded_headers="Authorization,Content-Length,x-ms-client-request-id,x-ms-request-id"
        )  # don't match on body for this test since we scrub the proj/deployment values
        client = TextAnalyticsClient(textanalytics_custom_text_endpoint, AzureKeyCredential(textanalytics_custom_text_key))
        docs = [
            {"id": "1", "language": "en", "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
            {"id": "2", "language": "en", "text": "David Schmidt, senior vice president--Food Safety, International Food Information Council (IFIC), Washington, D.C., discussed the physical activity component."},
            {"id": "3", "language": "en", "text": "I need a reservation for an indoor restaurant in China. Please don't stop the music. Play music and add it to my playlist"},
        ]

        response = client.begin_analyze_actions(
            docs,
            actions=[
                MultiCategoryClassifyAction(
                    project_name=textanalytics_multi_category_classify_project_name,
                    deployment_name=textanalytics_multi_category_classify_deployment_name
                )
            ],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        document_results = list(response)
        for doc_result in document_results:
            for result in doc_result:
                assert result.id
                assert not result.is_error
                assert not result.warnings
                assert result.statistics
                for classification in result.classifications:
                    assert classification.category
                    assert classification.confidence_score

    @pytest.mark.skipif(not is_public_cloud(), reason='Usgov and China Cloud are not supported')
    @TextAnalyticsCustomPreparer()
    @recorded_by_proxy
    def test_recognize_custom_entities(
            self,
            textanalytics_custom_text_endpoint,
            textanalytics_custom_text_key,
            textanalytics_custom_entities_project_name,
            textanalytics_custom_entities_deployment_name
    ):
        # this can be reverted to set_bodiless_matcher() after tests are re-recorded and don't contain these headers
        set_custom_default_matcher(
            compare_bodies=False, excluded_headers="Authorization,Content-Length,x-ms-client-request-id,x-ms-request-id"
        )  # don't match on body for this test since we scrub the proj/deployment values
        client = TextAnalyticsClient(textanalytics_custom_text_endpoint, AzureKeyCredential(textanalytics_custom_text_key))
        docs = [
            {"id": "1", "language": "en", "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
            {"id": "2", "language": "en", "text": "David Schmidt, senior vice president--Food Safety, International Food Information Council (IFIC), Washington, D.C., discussed the physical activity component."},
            {"id": "3", "language": "en", "text": "I need a reservation for an indoor restaurant in China. Please don't stop the music. Play music and add it to my playlist"},
        ]

        response = client.begin_analyze_actions(
            docs,
            actions=[
                RecognizeCustomEntitiesAction(
                    project_name=textanalytics_custom_entities_project_name,
                    deployment_name=textanalytics_custom_entities_deployment_name
                )
            ],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        document_results = list(response)
        for doc_result in document_results:
            for result in doc_result:
                assert result.id
                assert not result.is_error
                assert not result.warnings
                assert result.statistics
                for entity in result.entities:
                    assert entity.text
                    assert entity.category
                    assert entity.offset is not None
                    assert entity.length is not None
                    assert entity.confidence_score is not None

    @pytest.mark.skip("https://dev.azure.com/msazure/Cognitive%20Services/_workitems/edit/12409536 and https://github.com/Azure/azure-sdk-for-python/issues/21369")
    @TextAnalyticsPreparer()
    def test_custom_partial_error(
            self,
            textanalytics_custom_text_endpoint,
            textanalytics_custom_text_key,
            textanalytics_single_category_classify_project_name,
            textanalytics_single_category_classify_deployment_name,
            textanalytics_multi_category_classify_project_name,
            textanalytics_multi_category_classify_deployment_name,
            textanalytics_custom_entities_project_name,
            textanalytics_custom_entities_deployment_name
    ):
        client = TextAnalyticsClient(textanalytics_custom_text_endpoint, AzureKeyCredential(textanalytics_custom_text_key))
        docs = [
            {"id": "1", "language": "en", "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
            {"id": "2", "language": "en", "text": ""},
        ]

        response = client.begin_analyze_actions(
            docs,
            actions=[
                SingleCategoryClassifyAction(
                    project_name=textanalytics_single_category_classify_project_name,
                    deployment_name=textanalytics_single_category_classify_deployment_name
                ),
                MultiCategoryClassifyAction(
                    project_name=textanalytics_multi_category_classify_project_name,
                    deployment_name=textanalytics_multi_category_classify_deployment_name
                ),
                RecognizeCustomEntitiesAction(
                    project_name=textanalytics_custom_entities_project_name,
                    deployment_name=textanalytics_custom_entities_deployment_name
                )
            ],
            show_stats=True,
            polling_interval=self._interval(),
        ).result()

        document_results = list(response)
        assert len(document_results) == 2
        assert isinstance(document_results[0][0], SingleCategoryClassifyResult)
        assert isinstance(document_results[0][1], MultiCategoryClassifyResult)
        assert isinstance(document_results[0][2], RecognizeCustomEntitiesResult)
        assert document_results[1][0].is_error
        assert document_results[1][1].is_error
        assert document_results[1][2].is_error

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer()
    @recorded_by_proxy
    def test_analyze_continuation_token(self, client):
        docs = [
            {"id": "1", "language": "en", "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
            {"id": "2", "language": "en", "text": "David Schmidt, senior vice president--Food Safety, International Food Information Council (IFIC), Washington, D.C., discussed the physical activity component."},
            {"id": "3", "text": ""},
            {"id": "4", "language": "en", "text": "I need a reservation for an indoor restaurant in China. Please don't stop the music. Play music and add it to my playlist"},
        ]

        actions = [
            RecognizeEntitiesAction(),
            RecognizePiiEntitiesAction(),
            AnalyzeSentimentAction(),
            ExtractKeyPhrasesAction(),
        ]

        initial_poller = client.begin_analyze_actions(
            docs,
            actions=actions,
            show_stats=True,
            polling_interval=self._interval(),
        )

        cont_token = initial_poller.continuation_token()

        poller = client.begin_analyze_actions(
            None,
            None,
            continuation_token=cont_token,
            polling_interval=self._interval(),
        )
        response = poller.result()

        action_results = list(response)
        assert len(action_results) == len(docs)
        action_order = [
            _AnalyzeActionsType.RECOGNIZE_ENTITIES,
            _AnalyzeActionsType.RECOGNIZE_PII_ENTITIES,
            _AnalyzeActionsType.ANALYZE_SENTIMENT,
            _AnalyzeActionsType.EXTRACT_KEY_PHRASES,
        ]
        document_order = ["1", "2", "3", "4"]
        for doc_idx, document_results in enumerate(action_results):
            assert len(document_results) == 4
            for action_idx, document_result in enumerate(document_results):
                if doc_idx == 2:
                    assert document_result.id == document_order[doc_idx]
                    assert document_result.is_error
                else:
                    assert document_result.id == document_order[doc_idx]
                    assert document_result.statistics
                    assert self.document_result_to_action_type(document_result) == action_order[action_idx]

        initial_poller.wait()  # necessary so azure-devtools doesn't throw assertion error

    @pytest.mark.skipif(not is_public_cloud(), reason='Usgov and China Cloud are not supported')
    @TextAnalyticsCustomPreparer()
    def test_generic_action_error_no_target(
        self,
        **kwargs
    ):
        textanalytics_custom_text_endpoint = kwargs.pop("textanalytics_custom_text_endpoint")
        textanalytics_custom_text_key = kwargs.pop("textanalytics_custom_text_key")
        textanalytics_single_category_classify_project_name = kwargs.pop("textanalytics_single_category_classify_project_name")
        textanalytics_single_category_classify_deployment_name = kwargs.pop("textanalytics_single_category_classify_deployment_name")
        textanalytics_multi_category_classify_project_name = kwargs.pop("textanalytics_multi_category_classify_project_name")
        textanalytics_multi_category_classify_deployment_name = kwargs.pop("textanalytics_multi_category_classify_deployment_name")
        textanalytics_custom_entities_project_name = kwargs.pop("textanalytics_custom_entities_project_name")
        textanalytics_custom_entities_deployment_name = kwargs.pop("textanalytics_custom_entities_deployment_name")
        docs = [
            {"id": "1", "language": "en", "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
            {"id": "2", "language": "en", "text": ""},
        ]

        response = mock.Mock(
            status_code=200,
            headers={"Content-Type": "application/json", "operation-location": "https://fakeurl.com"}
        )

        path_to_mock_json_response = os.path.abspath(
            os.path.join(
                os.path.abspath(__file__),
                "..",
                "./mock_test_responses/action_error_no_target.json",
            )
        )
        with open(path_to_mock_json_response) as fd:
            mock_json_response = json.loads(fd.read())

        response.text = lambda encoding=None: json.dumps(mock_json_response)
        response.content_type = "application/json"
        transport = mock.Mock(send=lambda request, **kwargs: response)

        client = TextAnalyticsClient(textanalytics_custom_text_endpoint, AzureKeyCredential(textanalytics_custom_text_key), transport=transport)

        with pytest.raises(HttpResponseError) as e:
            response = list(client.begin_analyze_actions(
                docs,
                actions=[
                    SingleCategoryClassifyAction(
                        project_name=textanalytics_single_category_classify_project_name,
                        deployment_name=textanalytics_single_category_classify_deployment_name
                    ),
                    MultiCategoryClassifyAction(
                        project_name=textanalytics_multi_category_classify_project_name,
                        deployment_name=textanalytics_multi_category_classify_deployment_name
                    ),
                    RecognizeCustomEntitiesAction(
                        project_name=textanalytics_custom_entities_project_name,
                        deployment_name=textanalytics_custom_entities_deployment_name
                    )
                ],
                show_stats=True,
                polling_interval=self._interval(),
            ).result())
        assert e.value.message == "(InternalServerError) 1 out of 3 job tasks failed. Failed job tasks : v3.2-preview.2/custom/entities/general."

    @pytest.mark.skipif(not is_public_cloud(), reason='Usgov and China Cloud are not supported')
    @TextAnalyticsCustomPreparer()
    def test_action_errors_with_targets(
        self,
        **kwargs
    ):
        textanalytics_custom_text_endpoint = kwargs.pop("textanalytics_custom_text_endpoint")
        textanalytics_custom_text_key = kwargs.pop("textanalytics_custom_text_key")
        textanalytics_single_category_classify_project_name = kwargs.pop("textanalytics_single_category_classify_project_name")
        textanalytics_single_category_classify_deployment_name = kwargs.pop("textanalytics_single_category_classify_deployment_name")
        textanalytics_multi_category_classify_project_name = kwargs.pop("textanalytics_multi_category_classify_project_name")
        textanalytics_multi_category_classify_deployment_name = kwargs.pop("textanalytics_multi_category_classify_deployment_name")
        textanalytics_custom_entities_project_name = kwargs.pop("textanalytics_custom_entities_project_name")
        textanalytics_custom_entities_deployment_name = kwargs.pop("textanalytics_custom_entities_deployment_name")
        docs = [
            {"id": "1", "language": "en", "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
            {"id": "2", "language": "en", "text": ""},
        ]

        response = mock.Mock(
            status_code=200,
            headers={"Content-Type": "application/json", "operation-location": "https://fakeurl.com"}
        )

        # a mix of action errors to translate to doc errors, regular doc errors, and a successful response
        path_to_mock_json_response = os.path.abspath(
            os.path.join(
                os.path.abspath(__file__),
                "..",
                "./mock_test_responses/action_error_with_targets.json",
            )
        )
        with open(path_to_mock_json_response) as fd:
            mock_json_response = json.loads(fd.read())

        response.text = lambda encoding=None: json.dumps(mock_json_response)
        response.content_type = "application/json"
        transport = mock.Mock(send=lambda request, **kwargs: response)

        client = TextAnalyticsClient(textanalytics_custom_text_endpoint, AzureKeyCredential(textanalytics_custom_text_key), transport=transport)

        response = list(client.begin_analyze_actions(
            docs,
            actions=[
                RecognizeEntitiesAction(),
                ExtractKeyPhrasesAction(),
                RecognizePiiEntitiesAction(),
                RecognizeLinkedEntitiesAction(),
                AnalyzeSentimentAction(),
                ExtractSummaryAction(),
                RecognizePiiEntitiesAction(domain_filter="phi"),
                SingleCategoryClassifyAction(
                    project_name=textanalytics_single_category_classify_project_name,
                    deployment_name=textanalytics_single_category_classify_deployment_name
                ),
                MultiCategoryClassifyAction(
                    project_name=textanalytics_multi_category_classify_project_name,
                    deployment_name=textanalytics_multi_category_classify_deployment_name
                ),
                RecognizeCustomEntitiesAction(
                    project_name=textanalytics_custom_entities_project_name,
                    deployment_name=textanalytics_custom_entities_deployment_name
                ),
                SingleCategoryClassifyAction(
                    project_name=textanalytics_single_category_classify_project_name,
                    deployment_name=textanalytics_single_category_classify_deployment_name
                ),
            ],
            show_stats=True,
            polling_interval=self._interval(),
        ).result())
        assert len(response) == len(docs)
        for idx, result in enumerate(response[0]):
            assert result.id == "1"
            if idx == 10:
                assert not result.is_error
                assert isinstance(result, SingleCategoryClassifyResult)
            else:
                assert result.is_error
                assert result.error.code == "InvalidRequest"
                assert result.error.message == "Some error" + str(idx)  # confirms correct doc error order

        for idx, result in enumerate(response[1]):
            assert result.id == "2"
            assert result.is_error
            if idx == 10:
                assert result.error.code == "InvalidDocument"
                assert result.error.message == "Document text is empty."
            else:
                assert result.error.code == "InvalidRequest"
                assert result.error.message == "Some error" + str(idx)  # confirms correct doc error order

    @pytest.mark.skipif(not is_public_cloud(), reason='Usgov and China Cloud are not supported')
    @TextAnalyticsCustomPreparer()
    def test_action_job_failure(
            self,
            **kwargs
    ):
        textanalytics_custom_text_endpoint = kwargs.pop("textanalytics_custom_text_endpoint")
        textanalytics_custom_text_key = kwargs.pop("textanalytics_custom_text_key")
        textanalytics_custom_entities_project_name = kwargs.pop("textanalytics_custom_entities_project_name")
        textanalytics_custom_entities_deployment_name = kwargs.pop("textanalytics_custom_entities_deployment_name")
        docs = [
            {"id": "1", "language": "en",
             "text": "A recent report by the Government Accountability Office (GAO) found that the dramatic increase in oil and natural gas development on federal lands over the past six years has stretched the staff of the BLM to a point that it has been unable to meet its environmental protection responsibilities."},
            {"id": "2", "language": "en", "text": ""},
        ]

        response = mock.Mock(
            status_code=200,
            headers={"Content-Type": "application/json", "operation-location": "https://fakeurl.com"}
        )

        # action job failure with status=="failed", no partial results so we raise an exception in this case
        path_to_mock_json_response = os.path.abspath(
            os.path.join(
                os.path.abspath(__file__),
                "..",
                "./mock_test_responses/action_job_failure.json",
            )
        )
        with open(path_to_mock_json_response) as fd:
            mock_json_response = json.loads(fd.read())

        response.text = lambda encoding=None: json.dumps(mock_json_response)
        response.content_type = "application/json"
        transport = mock.Mock(send=lambda request, **kwargs: response)

        client = TextAnalyticsClient(textanalytics_custom_text_endpoint, AzureKeyCredential(textanalytics_custom_text_key),
                                     transport=transport)

        with pytest.raises(HttpResponseError) as e:
            response = list(client.begin_analyze_actions(
                docs,
                actions=[
                    RecognizeCustomEntitiesAction(
                        project_name=textanalytics_custom_entities_project_name,
                        deployment_name=textanalytics_custom_entities_deployment_name
                    ),
                ],
                show_stats=True,
                polling_interval=self._interval(),
            ).result())
            assert len(response) == len(docs)
        assert e.value.message == "(InternalServerError) 1 out of 1 job tasks failed. Failed job tasks : v3.2-preview.2/custom/entities/general."

    @TextAnalyticsPreparer()
    @TextAnalyticsClientPreparer(client_kwargs={"api_version": "v3.1"})
    @recorded_by_proxy
    def test_analyze_works_with_v3_1(self, client):
        docs = [{"id": "56", "text": ":)"},
                {"id": "0", "text": ":("},
                {"id": "19", "text": ":P"},
                {"id": "1", "text": ":D"}]

        response = client.begin_analyze_actions(
            docs,
            actions=[
                RecognizeEntitiesAction(),
                ExtractKeyPhrasesAction(),
                RecognizePiiEntitiesAction(),
                RecognizeLinkedEntitiesAction(),
                AnalyzeSentimentAction()
            ],
            polling_interval=self._interval(),
        ).result()

        results = list(response)
        assert len(results) == len(docs)

        document_order = ["56", "0", "19", "1"]
        action_order = [
            _AnalyzeActionsType.RECOGNIZE_ENTITIES,
            _AnalyzeActionsType.EXTRACT_KEY_PHRASES,
            _AnalyzeActionsType.RECOGNIZE_PII_ENTITIES,
            _AnalyzeActionsType.RECOGNIZE_LINKED_ENTITIES,
            _AnalyzeActionsType.ANALYZE_SENTIMENT,
        ]
        for doc_idx, document_results in enumerate(results):
            assert len(document_results) == 5
            for action_idx, document_result in enumerate(document_results):
                assert document_result.id == document_order[doc_idx]
                assert not document_result.is_error
                assert self.document_result_to_action_type(document_result) == action_order[action_idx]
