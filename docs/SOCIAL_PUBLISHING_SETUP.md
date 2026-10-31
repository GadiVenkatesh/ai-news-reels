# Social publishing setup

The existing Generate AI News Reel workflow still produces the fixed 60-second, 1080x1920 MP4. The separate Publish AI News Reel workflow downloads that generated artifact and publishes it.

## How it works

1. Generate AI News Reel completes successfully.
2. Publish AI News Reel downloads the generated MP4 and adjacent JSON metadata.
3. app/publish.py prepares platform-specific title, description, source attribution and hashtags using the generated story metadata.
4. The YouTube Data API uploads the MP4 using OAuth 2.0 refresh-token credentials.
5. For Instagram, the workflow uploads the MP4 to a private S3 bucket and creates a short-lived presigned GET URL. Meta fetches the video URL, the workflow polls the Reel container until FINISHED, and then calls media_publish.
6. The workflow attempts to delete the temporary S3 object and saves publishing-report.json as an Actions artifact.

The workflow is separate from the generator to keep rendering and publishing independently observable.

## Required GitHub repository secrets

### YouTube

- YOUTUBE_CLIENT_ID
- YOUTUBE_CLIENT_SECRET
- YOUTUBE_REFRESH_TOKEN

Enable YouTube Data API v3 in a Google Cloud project, configure an OAuth consent screen, create an OAuth client, and authorize the YouTube channel with the youtube.upload scope. Store the resulting refresh token as a GitHub Actions secret. Do not commit OAuth client files or tokens.

### Instagram + temporary S3 hosting

- INSTAGRAM_USER_ID
- INSTAGRAM_ACCESS_TOKEN
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- AWS_REGION
- PUBLISH_S3_BUCKET

The Instagram account must be a professional Business or Creator account with publishing access configured in a Meta developer app. For the Facebook Login integration, link the Instagram professional account to a Facebook Page and grant the permissions required by the selected Meta API setup, including instagram_content_publish and the relevant account/page read permissions. Use a token with the account and publishing access required by your app.

Create a private S3 bucket. The publishing workflow uploads one object, creates a time-limited signed GET URL for Meta's fetch, and deletes the object after publishing. The IAM principal should have only the necessary S3 PutObject, GetObject (for presigning), and DeleteObject permissions on the publishing prefix/bucket. Avoid public bucket access.

## GitHub Actions repository variables

- META_GRAPH_API_VERSION: set this to a currently supported Graph API version, e.g. the version selected in your Meta app. Do not leave the workflow's vXX.X placeholder.
- YOUTUBE_PRIVACY_STATUS: recommended first-run value private; set public only when ready for unattended public release.
- YOUTUBE_CATEGORY_ID: defaults to 28 (Science & Technology).

## Run

- Automatic: a successful Generate AI News Reel run triggers publishing to both platforms.
- Manual: open Actions -> Publish AI News Reel -> Run workflow, choose both/youtube/instagram and type PUBLISH.
- Manual publishing downloads the named artifact from the supplied generation run ID. Supply the Generate workflow run ID in artifact_run_id.

YouTube's privacy setting defaults to private. The automatic workflow uses that configured value. For a cautious first test, set YOUTUBE_PRIVACY_STATUS=private and use a test Instagram account or turn off Instagram until credentials are verified.

## Metadata and hashtags

The publisher uses the generated story title/source/URL, not a second unrelated search. It creates concise Telugu or English captions, credits the source publisher and links to the original story. Hashtags are a small topic-relevant starter set; they are not live popularity rankings and should be reviewed for the channel's audience. Do not add unrelated trending tags. YouTube's tags and description are set separately from Instagram's caption.

This is organic content publishing, not paid advertising or Ads Manager campaign creation. It does not create ad campaigns, spend budget, guarantee reach, or claim that hashtags are guaranteed to increase views.

## Important deployment notes

- Instagram Reels API publishing is only for eligible professional accounts and requires the media to be fetchable by Meta. The workflow uses S3 presigned URL for this.
- Ensure the video meets Meta's current file-size, codec, aspect-ratio, audio and duration requirements. The generator produces 1080x1920 H.264/AAC, 60 seconds.
- Keep the Meta Graph API version current and supported by the Meta app.
- GitHub's workflow_run trigger runs with the default branch context. Protect the main branch and review workflow changes. Limit publishing secrets to the minimum trusted actors and use GitHub environments/required reviewers for production credentials.
- GitHub Actions artifacts are retention-limited; publishing is triggered immediately after generation, not after downloading the artifact manually.
- Instagram may fail independently of YouTube. Check the report artifact and job logs.
