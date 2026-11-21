"""CloudWatch alarms -> SNS email (P5-03).

The email address is never committed (the repository is public): pass it at deploy time with
`-c alarmEmail=you@example.com` (scripts/deploy.ps1 -AlarmEmail). Without it the alarms still
exist and show in the CloudWatch console, but nobody is emailed.
"""

from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from aws_cdk import aws_sqs as sqs
from constructs import Construct

FIVE_MIN = Duration.minutes(5)


class Monitoring(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        functions: dict[str, lambda_.IFunction],
        http_api: apigw.HttpApi,
        chat_function: lambda_.IFunction,
        dead_letter_queue: sqs.IQueue,
        alarm_email: str | None,
    ) -> None:
        super().__init__(scope, construct_id)
        self.topic = sns.Topic(self, "AlarmTopic", display_name="Clouddocs alarms")
        self.topic.apply_removal_policy(RemovalPolicy.DESTROY)
        if alarm_email:
            self.topic.add_subscription(subs.EmailSubscription(alarm_email))
        action = cw_actions.SnsAction(self.topic)
        self.alarms: list[cw.Alarm] = []

        def alarm(name: str, metric: cw.IMetric, threshold: float, description: str) -> None:
            a = cw.Alarm(
                self,
                name,
                metric=metric,
                threshold=threshold,
                evaluation_periods=1,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
                alarm_description=description,
            )
            a.add_alarm_action(action)
            self.alarms.append(a)

        for label, fn in functions.items():
            alarm(
                f"{label}Errors",
                fn.metric_errors(period=FIVE_MIN, statistic="Sum"),
                1,
                f"The {label} Lambda raised an unhandled error (see its log group).",
            )

        alarm(
            "Api5xx",
            http_api.metric_server_error(period=FIVE_MIN, statistic="Sum"),
            1,
            "The API returned a 5xx response.",
        )
        alarm(
            "Api4xxSpike",
            http_api.metric_client_error(period=FIVE_MIN, statistic="Sum"),
            50,
            "50+ client errors in 5 minutes: throttling (429), failed logins or probing.",
        )
        alarm(
            "ChatSlow",
            chat_function.metric_duration(period=FIVE_MIN, statistic="p90"),
            20_000,
            "Chat answers are near the 29 s timeout (p90 >= 20 s).",
        )
        alarm(
            "IngestDLQNotEmpty",
            dead_letter_queue.metric_approximate_number_of_messages_visible(
                period=FIVE_MIN, statistic="Maximum"
            ),
            1,
            "An upload could not be processed after 3 tries (ingest dead-letter queue).",
        )
