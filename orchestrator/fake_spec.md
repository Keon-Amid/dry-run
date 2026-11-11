# Shortlink (STUB spec for the fake builder; P2's spec.md replaces it)

## Step 1
Create a FastAPI app with a health endpoint.

## Step 2
POST /links creates a short link; codes are 6 digits.

## Step 3
Links expire after 30 days.

## Step 4
GET /<code> redirects and counts the click.

## Step 5
Users may pick an alias instead of a generated code.

## Step 6
GET /links/<code>/stats returns the click count.

## Step 7
Add tests for every endpoint.
