// https://github.com/googleworkspace/apps-script-oauth2

function fetchDataAndAppend_adafruit() {
    // OAuth2 Configuration
    var clientId = '190892857225-tejt3vboukfutifvidtgo2ne0tj1telt.apps.googleusercontent.com'; 
    var clientSecret = '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'; 
    var oauth2 = OAuth2.createService('AdafruitQuotes') 
        .setAuthorizationBaseUrl('https://www.adafruit.com/api/quotes.php') 
        .setTokenUrl('https://www.adafruit.com/api/quotes.php') 
        .setClientId(clientId)
        .setClientSecret(clientSecret)
        .setPropertyStore(PropertiesService.getUserProperties());

  // Get the spreadsheet and sheet
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getActiveSheet();

  // Fetch the quote from the API
  var response = UrlFetchApp.fetch("https://www.adafruit.com/api/quotes.php"); 
  Logger.log("respons=%s",response)
  var resp = JSON.parse(response.getContentText());

  // Get the current date and time
  var now = new Date();

  // Append the quote and timestamp to the sheet
  sheet.appendRow([now, resp[0].author, resp[0].text]);
}

function fetchDataAndAppend() {
    // OAuth2 Configuration
    const HUBITAT_DATA = 'https://cloud.hubitat.com/api/d94da070-d0cc-4c39-bd60-2f074b23f990/apps/493/devices/all?access_token=fdf1fff8-390b-4399-baf0-d3ebc86b7543';
    const clientId = '190892857225-tejt3vboukfutifvidtgo2ne0tj1telt.apps.googleusercontent.com'; 
    const clientSecret = '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'; 
    var oauth2 = OAuth2.createService('AdafruitQuotes') 
        .setAuthorizationBaseUrl('https://www.adafruit.com/api/quotes.php') 
        .setTokenUrl('https://www.adafruit.com/api/quotes.php') 
        .setClientId(clientId)
        .setClientSecret(clientSecret)
        .setPropertyStore(PropertiesService.getUserProperties());

  // Get the spreadsheet, sheet and headers
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getActiveSheet();
  var header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var updatedHeader = false;

  // Fetch the temperature data from the API
  const response = UrlFetchApp.fetch(HUBITAT_DATA); 
  const hubData = JSON.parse(response.getContentText());

  // Find all temperatures and append new headers
  const temps = {};
  hubData.forEach(e => {
    if (e.attributes.temperature) {
        temps[e.label] = e.attributes.temperature;
        if (!header.includes(e.label)) {
            header.push(e.label);
            updatedHeader = true;
        }
    }
  });


  // Get the current date and time
  const now = new Date();
  const newRow = [now, ...header.slice(1).map(label => temps[label] || "")];

  if (newRow.length !== header.length) {
    throw new Error("Row and header lengths do not match!");
  }

  // Update the header if changed
  if (updatedHeader) {
    Logger.log("Updated Header: " + header);
    sheet.getRange(1, 1, 1, header.length).setValues([header]);
  }

  // Append the quote and timestamp to the sheet
  sheet.appendRow(newRow);
  Logger.log("New Row: " + newRow);
}

// Run the function every minute
function createTrigger() {
  ScriptApp.newTrigger("fetchDataAndAppend")
    .timeBased()
    .everyMinutes(1)
    .create();
}
