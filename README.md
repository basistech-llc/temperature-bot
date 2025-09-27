# Notes

Getting data from the Hubitats:
https://community.hubitat.com/t/dummies-questions-on-how-to-get-started-with-maker-api/52822
https://community.hubitat.com/t/consuming-rest-api/100981
https://hubitat.com/home-automation/maker-api
https://community.hubitat.com/t/api-restful-documentation/138586
https://community.hubitat.com/t/how-to-use-api-to-access-variables/122717


https://github.com/dpb587/hubitat-cli


# Tech Stack

## Database
- Maintains temperature and fan settings for all devices
- Temperatures are stored with run-length encoding to prevent database explosion


## Rules Engine

## Periodic Jobs

### Temperature Bot
- Runs every minute
- Queries every sensor and puts the results into the database.
