/**
 * Feedback relay for apps that use feedback.py (Blockliner and others).
 * Runs as YOU on Google's servers, so the app never holds a password or key.
 * Setup: docs/feedback-relay/README.md
 */
var ALLOWED_TO = ['support.somore100@gmail.com'];   // the only address it will ever mail
var MAX_BODY = 12000;
var MAX_PER_HOUR = 30;                               // all apps together

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var to = String(data.to || '');
    var subject = String(data.subject || '').replace(/[\r\n]+/g, ' ').slice(0, 200);
    var body = String(data.body || '').slice(0, MAX_BODY);
    if (ALLOWED_TO.indexOf(to) < 0) return reply_(false, 'Address not allowed.');
    if (!subject || body.length < 10) return reply_(false, 'Empty report.');
    if (!allow_()) return reply_(false, 'Too many reports right now, try again later.');
    MailApp.sendEmail(to, subject, body, {name: String(data.app || 'Feedback')});
    return reply_(true, 'sent');
  } catch (err) {
    return reply_(false, 'Bad request.');
  }
}

function allow_() {                                  // simple hourly limit
  var props = PropertiesService.getScriptProperties();
  var hour = Math.floor(Date.now() / 3600000);
  var key = 'count_' + hour;
  var n = Number(props.getProperty(key) || 0);
  if (n >= MAX_PER_HOUR) return false;
  props.setProperty(key, String(n + 1));
  return true;
}

function reply_(ok, msg) {
  return ContentService.createTextOutput(JSON.stringify(ok ? {ok: true} : {ok: false, error: msg}))
    .setMimeType(ContentService.MimeType.JSON);
}
