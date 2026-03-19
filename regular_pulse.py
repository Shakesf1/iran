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
    subject = "Strategic Pulse: Day 20 of Iran War"
    
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
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >Today marks the 20th day of the conflict. We are entering the most dangerous phase of any war: </span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'><b>Normalization.</b></span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'>
      As the initial shock fades from the headlines, public attention wavers but the data tells a different story. As impact on global markets will now become real. </span
    >
  </p>
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'>On </span
    ><a href="http://www.warescalation.com/?campaign=newsletter" title="http://www.warescalation.com/"
      ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,238)'><u>warescalation.com</u></span></a>
      <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >, the metrics remain relentless. Despite claims from Washington and Jerusalem that the Iranian command structure
      is &quot;on its knees&quot; following the liquidation of senior leaders, the reality tells us different. Iran’s
      launch tempo has not decayed. It has stabilized:</span>
  </p>
    <div style="text-align: left; margin: 20px 0;">
        <img src="cid:pulse-chart" alt="Iran Attacks" width="510" height="270" />
    </div>
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'>
      The most critical data point is the </span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'><b>Strait of Hormuz</b></span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >. Total transit volume remains at historic lows. Our AIS tracking shows a striking anomaly: the few ships
      currently transiting are almost exclusively members of the “Shadow Fleet” or vessels taking non-standard routes
      under guidance of Iran (Indian ships earlier in the week). This implies a &quot;negotiated&quot; crossing, </span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >Iran is still acting as the gatekeeper.</span
    >
  </p>
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >Geopolitically, the implications are binary. The U.S. and Israel can strike the heartland, but if they cannot
      guarantee some ships to pass through Hormuz they are losing the strategic war. This mirrors the </span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'><b>Tanker Wars of the 1980s</b></span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >, but with a modern twist: Iran doesn&#39;t need to physically block the Strait; they only need to keep insurance
      premiums high enough to make it a &quot;no-go&quot; zone for Western capital. To avoid a visible strategic defeat,
      the U.S. will need to escalate and institute navy convoys through the Strait.
    </span>
  </p>
  <p style="margin-top:0pt;margin-bottom:10pt;border:medium">
    <span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >Secondly, for global markets it’s all about inflation. PPI yesterday printed significantly higher than expected
      and that was pre-Iran War (February). </span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >Interesting research was done by the FED in 2024 (last updated): “</span
    ><a
      href="https://www.federalreserve.gov/econres/notes/feds-notes/oil-price-shocks-and-inflation-in-a-dsge-model-of-the-global-economy-20240802.html"
      title="FED Research: Oil Price Shocks and Inflation in a DSGE Model for the Global Economy"
      ><span style='font-family:"Arial";font-size:11pt;color:rgb(5,99,193)'
        ><u>Oil Price Shocks and Inflation in a DSGE Model for the Global Economy</u></span
      ></a
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >”. This links Oil Price Shocks to inflation. Oil impacts food prices, wages (due to cost of living) and
      expectations. The impac</span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >t is larger when the cause is not transitory but long lasting. Central Banks are in a bind. They can fight
      inflation (higher rates) which hurts growth or support economic growth (which boosts inflation). Rate cuts are
      less likely (increases more, Polymarke</span
    ><span style='font-family:"Arial";font-size:10pt;color:rgb(0,0,0)'
      >t assigns 40+% probability to ECB hiking rates) and policy will become reactive. Long story short, the real
      economic impact worsens the longer the war continues. Impacting global growth and inflation, effectively making
      stagflation more likely by the day.
    </span>
  </p>
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