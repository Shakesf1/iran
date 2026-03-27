import os
import time
import resend
from dotenv import load_dotenv
from supabase import create_client, Client
load_dotenv()
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# Load variables from .env

resend.api_key = os.getenv("RESEND_API_KEY")

current_dir = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(current_dir, "static", "iranstrikes-19mar.png")

def get_subscribers():
    try:
        # SELECT email FROM subscribers
        response = supabase.table("subscribers").select("email").execute()
         
        # Flatten the list of dictionaries [{'email': '...'}, ...] into ['...', '...']
        email_list = [row['email'] for row in response.data]
        return email_list
    except Exception as e:
        print(f"❌ Database error: {e}")
        return []

def send_newsletter():
    subject = "Warescalation.com - Now with live odds"
    
    # 1. Read the image file as bytes
    try:
        with open(image_path, "rb") as f:
            image_data = list(f.read()) # Resend Python SDK expects a list of bytes
    except FileNotFoundError:
        print(f"❌ Error: Image not found at {image_path}")
        return

    # Your HTML content (keep your existing HTML, just ensuring the CID matches)
    html_content = """
<div dir="ltr">
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'>Dear Reader,</span>
  </p>
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
      Today marks is the <b>28th day of the conflict</b>: 
  </p>
  <p>
  A lot has happened since the last newsletter. I promised not to spam your inbox, but I also want to share the latest updates and insights with you. So here we are. 
  For the loyal newsletter readers you get the first view: <br/>
  1) Data on ships crossing through Bab Al-Mandeb Strait, unaffected for now but under constant threat by the Houthis and another weapon in arsenal of Iran(s proxies).<br/>
  2) Data from Polymarket on relevant bets regarding the war<br/>
        </p>
<p><img src="cid:polymarket" alt="Polymarket" /></p>

  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >If you find it interesting, please share the site – </span
    ><a href="http://www.warescalation.com/?campaign=newsletter" title="http://www.warescalation.com"
      ><span style='font-family:"Arial";font-size:11pt;color:rgb(5,99,193)'><u>warescalation.com</u></span></a
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'>
      – with your friends! Don’t keep all the good stuff to yourself. :-) </span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'>Feedback is also very much appreciated. </span>
  </p>
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'>Kind regards,</span>
  </p>
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'>Stan</span>
  </p>
<hr style="border: 0; border-top: 1px solid #000; margin: 10pt 0;">
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >Newsletter is send intermittently, not daily.
    </span>
  </p>
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >To unsubscribe, please reply to this email with &quot;UNSUBSCRIBE&quot;.<br /><span> 
      <hr style="border: 0; border-top: 1px solid #000; margin: 10pt 0;">
  </p>
  <br />
</div>

 
    """

    subscribers = ["stan@warescalation.com"]
    subscribers = get_subscribers()
    print(subscribers)
    for email in subscribers:
        try:
            resend.Emails.send({
                "from": "Stan <stan@warescalation.com>",
                "to": email,
                "subject": subject,
                "html": html_content,
                "attachments": [
                    {
                        "filename": "iranstrikes-19mar.png",
                        "content": image_data,  # FIX: Use 'content' (bytes) instead of 'path'
                        "content_id": "pulse-chart" 
                    }
                ]
            })
            print(f"✅ Sent to {email}")
            time.sleep(1) 
        except Exception as e:
            print(f"❌ Error sending to {email}: {e}")

if __name__ == "__main__":
    send_newsletter()