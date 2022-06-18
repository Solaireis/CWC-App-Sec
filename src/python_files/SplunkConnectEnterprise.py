import sys
import pathlib
sys.path.insert(0, pathlib.Path(__file__).parent.absolute().joinpath("..", "lib"))
import splunklib.client as client
HOST = "localhost"
PORT = 8089
USERNAME = "CourseFinity" # the log in username we will be using for the splunk
PASSWORD = ';aE9"n%EpCQ>x7$!' # the password we will be using for the splunk 

# Create a Service instance and log in 
service = client.connect(
    host=HOST,
    port=PORT,
    username=USERNAME,
    password=PASSWORD)

# Print installed apps to the console to verify login
for app in service.apps:
    print (app.name)