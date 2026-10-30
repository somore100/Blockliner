# Feedback relay (5 minutes, free)

The app never contains an email password. It posts the report to this small script, which runs
under your Google account and mails it to `support.somore100@gmail.com`. If the relay is not set
up or is unreachable, the app opens the user's own email app with the report filled in instead.

1. Sign in to the Google account that should send the mail (support.somore100@gmail.com works).
2. Open https://script.google.com, **New project**, delete the sample code, paste `relay.gs`.
3. **Deploy > New deployment > Web app**. Execute as: **Me**. Who has access: **Anyone**. Deploy.
   Google asks you to authorise sending email once.
4. Copy the **Web app URL** (it starts with `https://script.google.com/macros/s/`).
5. Put it in `feedback_config.json` next to the program:

   ```json
   { "relay_url": "https://script.google.com/macros/s/XXXX/exec" }
   ```

   (Or set `"feedback_relay_url"` in the app's settings file.) Rebuild so the file is bundled.
6. Test: Help > Leave Feedback, fill it in, Send. A mail should arrive within seconds.

Notes
- The relay only mails addresses listed in `ALLOWED_TO` and caps reports at 30 per hour, so a
  leaked URL cannot be used as a general spam mailer.
- To reuse it in another app, add that app's support address to `ALLOWED_TO` (or keep one inbox)
  and give the app its own `FeedbackConfig` (see `feedback.py`).
- Changing `relay.gs` later needs **Deploy > Manage deployments > Edit > New version**.
