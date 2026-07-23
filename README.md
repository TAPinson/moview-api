# moview-api

Python GraphQL API intended for AWS Lambda. The handler supports two invocation shapes:

- HTTP GraphQL requests from API Gateway, Lambda Function URLs, or local tools.
- AWS AppSync Lambda resolver events, so fields can be tested directly in the AppSync console.

## Local setup

```bash
cd moview-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Run tests

```bash
pytest
```

## Try the handler locally

```bash
python3 -m moview_api.handler events/http-graphql.json
python3 -m moview_api.handler events/appsync-health.json
```

## Deploy with SAM

```bash
sam build
sam deploy --guided
```

The SAM template deploys the Lambda function and configures AppSync in the same CloudFormation stack:

- Cognito User Pool with email-based self sign-up and verification.
- AppSync GraphQL API using Cognito User Pool authentication.
- GraphQL schema for health, users, movies, likes, and watchlist operations.
- Lambda data source connected to `MoviewApiFunction`.
- Lambda resolvers for AppSync query and mutation fields.

After deploy, configure the UI with these stack outputs:

- `MoviewUserPoolId`
- `MoviewUserPoolClientId`
- `MoviewGraphQLApiUrl`

The AppSync endpoint requires a valid Cognito user token. In the AppSync query console, authenticate with a Cognito user and run:

```graphql
query Health {
  health {
    ok
    service
  }
}
```
