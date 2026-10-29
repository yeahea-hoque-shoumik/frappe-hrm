"""Load sample HR data into the demo site.

deploy.sh runs this for you. To run it by hand, finish the setup wizard first:

    docker compose exec frappe bash /workspace/seed.sh

Creates, for the default company: a holiday list, 12 employees in a reporting
hierarchy, leave allocations and applications, two weeks of attendance, a salary
structure with assignments, a payroll run for last month (salary slips left as
draft) and two job openings with applicants. Running it again does nothing.
"""

import os
import random

import frappe
from frappe.utils import add_days, add_months, add_years, get_first_day, get_last_day, getdate, today

# Days off each week. Change to e.g. ("Friday", "Saturday") to match your region.
WEEKLY_OFFS = ("Saturday", "Sunday")

# first, last, gender, birth year, department, designation, years employed, manager (index), base pay
EMPLOYEES = [
	("Olivia", "Bennett", "Female", 1978, "Management", "CEO", 8, None, 9000),
	("Marcus", "Reid", "Male", 1984, "Human Resources", "Manager", 6, 0, 5200),
	("Priya", "Nair", "Female", 1986, "Research & Development", "Manager", 6, 0, 6000),
	("Daniel", "Okafor", "Male", 1982, "Sales", "Manager", 5, 0, 5500),
	("Sofia", "Martinez", "Female", 1990, "Accounts", "Accountant", 4, 0, 4200),
	("Ethan", "Clarke", "Male", 1993, "Research & Development", "Engineer", 4, 2, 4500),
	("Aisha", "Rahman", "Female", 1995, "Research & Development", "Engineer", 3, 2, 4300),
	("Lucas", "Fischer", "Male", 1997, "Research & Development", "Engineer", 1, 2, 3800),
	("Hannah", "Kim", "Female", 1994, "Sales", "Associate", 3, 3, 3200),
	("Noah", "Patel", "Male", 1998, "Sales", "Associate", 2, 3, 3000),
	("Grace", "Turner", "Female", 1996, "Human Resources", "Associate", 2, 1, 3100),
	("Samuel", "Osei", "Male", 2000, "Accounts", "Analyst", 0, 4, 2800),
]

LEAVE_ALLOCATIONS = {"Casual Leave": 12, "Sick Leave": 10, "Privilege Leave": 15}

rng = random.Random(42)


def run():
	if not frappe.db.get_single_value("System Settings", "setup_complete"):
		print("Finish the setup wizard in the browser first, then run this again.")
		return

	company = frappe.get_doc("Company", get_company())
	if frappe.db.exists("Employee", {"company": company.name, "personal_email": email_for(EMPLOYEES[0])}):
		print(f"Demo data already exists for {company.name}, nothing to do.")
		return

	print(f"Loading demo data into {company.name}...")
	holiday_list = make_holiday_list(company)
	employees = make_employees(company, holiday_list)
	allocate_leaves(company, employees)
	make_leave_applications(employees)
	mark_attendance(company, employees, holiday_list)
	make_payroll(company, employees)
	make_recruitment(company)
	frappe.db.commit()
	print("Done. Log in and open the HR workspace to explore.")


def set_admin_email():
	"""Set the Administrator account's email address from ADMIN_EMAIL."""
	email = (os.environ.get("ADMIN_EMAIL") or "").strip()
	if not email:
		return
	frappe.utils.validate_email_address(email, throw=True)
	if frappe.db.get_value("User", "Administrator", "email") != email:
		frappe.db.set_value("User", "Administrator", "email", email)
		frappe.db.commit()
	print(f"Administrator email: {email}")


def complete_setup():
	"""Finish the setup wizard without the browser. Settings come from DEMO_* environment variables."""
	if frappe.db.get_single_value("System Settings", "setup_complete"):
		print("Setup wizard already done, skipping.")
		return

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	company = os.environ.get("DEMO_COMPANY") or "Acme Demo"
	abbr = os.environ.get("DEMO_COMPANY_ABBR") or "".join(word[0] for word in company.split()).upper()[:5]
	year = getdate(today()).year
	result = setup_complete(
		{
			"language": "English",
			"country": os.environ.get("DEMO_COUNTRY") or "United States",
			"currency": os.environ.get("DEMO_CURRENCY") or "USD",
			"timezone": os.environ.get("DEMO_TIMEZONE") or "America/New_York",
			"company_name": company,
			"company_abbr": abbr,
			"chart_of_accounts": "Standard",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"enable_telemetry": 0,
		}
	)
	frappe.db.commit()

	if not frappe.db.get_single_value("System Settings", "setup_complete"):
		raise SystemExit(f"Setup wizard failed: {result}")
	print(f"Setup done: company {company} ({abbr})")


def get_company():
	company = frappe.defaults.get_global_default("company")
	if not company:
		company = frappe.db.get_value("Company", {}, "name", order_by="creation")
	return company


def email_for(row):
	return f"{row[0]}.{row[1]}@example.com".lower()


def make_holiday_list(company):
	this_year = getdate(today()).year
	name = f"Demo Holidays {this_year}"
	if not frappe.db.exists("Holiday List", name):
		doc = frappe.new_doc("Holiday List")
		doc.holiday_list_name = name
		# Cover last year too, so backdated records and recent hires fall inside it
		doc.from_date = f"{this_year - 1}-01-01"
		doc.to_date = f"{this_year}-12-31"
		for day in WEEKLY_OFFS:
			doc.weekly_off = day
			doc.get_weekly_off_dates()
		doc.insert()

	company.db_set("default_holiday_list", name)
	# Since version 16, holiday lists apply through a submitted Holiday List Assignment
	if frappe.db.exists("DocType", "Holiday List Assignment") and not frappe.db.exists(
		"Holiday List Assignment", {"assigned_to": company.name, "holiday_list": name, "docstatus": 1}
	):
		assignment = frappe.new_doc("Holiday List Assignment")
		assignment.update(
			{
				"applicable_for": "Company",
				"assigned_to": company.name,
				"holiday_list": name,
				"from_date": f"{this_year - 1}-01-01",
			}
		)
		assignment.insert()
		assignment.submit()
	print(f"  holiday list: {name}")
	return name


def get_or_make_department(name, company):
	department = frappe.db.get_value("Department", {"department_name": name, "company": company.name})
	if department:
		return department

	doc = frappe.new_doc("Department")
	doc.department_name = name
	doc.company = company.name
	doc.parent_department = frappe.db.get_value("Department", {"is_group": 1, "lft": 1})
	doc.insert()
	return doc.name


def get_or_make_designation(name):
	if not frappe.db.exists("Designation", name):
		frappe.get_doc({"doctype": "Designation", "designation_name": name}).insert()
	return name


def make_employees(company, holiday_list):
	employees = []
	start_of_year = getdate(f"{getdate(today()).year}-01-01")
	for i, row in enumerate(EMPLOYEES):
		first, last, gender, birth_year, department, designation, years, manager, base = row

		joined = add_years(today(), -years) if years else add_months(today(), -3)
		joined = getdate(add_days(joined, -rng.randint(0, 60)))
		if not years:
			# A recent hire, but keep them inside this year so leave and payroll data line up
			joined = max(joined, start_of_year)

		doc = frappe.new_doc("Employee")
		doc.update(
			{
				"first_name": first,
				"last_name": last,
				"gender": gender,
				"date_of_birth": f"{birth_year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
				"date_of_joining": joined,
				"company": company.name,
				"department": get_or_make_department(department, company),
				"designation": get_or_make_designation(designation),
				"employment_type": "Intern" if not years else "Full-time",
				"holiday_list": holiday_list,
				"personal_email": email_for(row),
				"cell_number": f"+1555{rng.randint(1000000, 9999999)}",
				"status": "Active",
				"reports_to": employees[manager]["name"] if manager is not None else None,
			}
		)
		doc.insert()
		employees.append(frappe._dict(name=doc.name, joined=joined, base=base))

	print(f"  employees: {len(employees)}")
	return employees


def allocate_leaves(company, employees):
	# Backdated leave goes up to ~2 months back, which can reach into last year
	years = range(getdate(add_days(today(), -70)).year, getdate(today()).year + 1)
	count = 0
	for emp in employees:
		for year in years:
			year_start, year_end = getdate(f"{year}-01-01"), getdate(f"{year}-12-31")
			if emp.joined > year_end:
				continue
			for leave_type, days in LEAVE_ALLOCATIONS.items():
				if not frappe.db.exists("Leave Type", leave_type):
					continue
				doc = frappe.new_doc("Leave Allocation")
				doc.update(
					{
						"employee": emp.name,
						"leave_type": leave_type,
						"from_date": max(year_start, emp.joined),
						"to_date": year_end,
						"new_leaves_allocated": days,
						"company": company.name,
					}
				)
				doc.insert()
				doc.submit()
				count += 1
	print(f"  leave allocations: {count}")


def working_days_back(start, count):
	"""The `count` working days ending on or before `start`, oldest first."""
	days, day = [], getdate(start)
	while len(days) < count:
		if day.strftime("%A") not in WEEKLY_OFFS:
			days.append(day)
		day = add_days(day, -1)
	return list(reversed(days))


def make_leave_applications(employees):
	approved = [
		(5, "Casual Leave", 30, 2, "Family event"),
		(6, "Sick Leave", 21, 1, "Fever"),
		(8, "Privilege Leave", 45, 3, "Vacation"),
		(9, "Casual Leave", 9, 1, "Personal errand"),
		(10, "Sick Leave", 4, 2, "Doctor's appointment"),
		(4, "Privilege Leave", 60, 3, "Travel"),
	]
	for idx, leave_type, days_ago, length, reason in approved:
		dates = working_days_back(add_days(today(), -days_ago), length)
		make_leave_application(employees[idx], leave_type, dates[0], dates[-1], reason, "Approved")

	# Waiting for approval, so the approval flow can be shown
	for idx, leave_type, days_ahead, reason in [(7, "Casual Leave", 7, "Moving house"), (3, "Privilege Leave", 14, "Holiday")]:
		start = getdate(add_days(today(), days_ahead))
		while start.strftime("%A") in WEEKLY_OFFS:
			start = add_days(start, 1)
		make_leave_application(employees[idx], leave_type, start, start, reason, "Open")

	print(f"  leave applications: {len(approved)} approved, 2 waiting for approval")


def make_leave_application(emp, leave_type, from_date, to_date, reason, status):
	if getdate(from_date) < emp.joined:
		return
	doc = frappe.new_doc("Leave Application")
	doc.update(
		{
			"employee": emp.name,
			"leave_type": leave_type,
			"from_date": from_date,
			"to_date": to_date,
			"description": reason,
			"status": status,
			"posting_date": min(getdate(from_date), getdate(today())),
		}
	)
	doc.insert()
	if status == "Approved":
		doc.submit()


def mark_attendance(company, employees, holiday_list):
	days = working_days_back(add_days(today(), -1), 10)
	holidays = set(frappe.get_all("Holiday", {"parent": holiday_list}, pluck="holiday_date"))
	count = 0
	for emp in employees:
		for day in days:
			if day < emp.joined or day in holidays:
				continue
			# Leave applications already marked these days as On Leave
			if frappe.db.exists("Attendance", {"employee": emp.name, "attendance_date": day, "docstatus": 1}):
				continue
			roll = rng.random()
			status = "Present" if roll < 0.85 else "Work From Home" if roll < 0.95 else "Absent"
			doc = frappe.new_doc("Attendance")
			doc.update(
				{"employee": emp.name, "attendance_date": day, "status": status, "company": company.name}
			)
			doc.insert()
			doc.submit()
			count += 1
	print(f"  attendance records: {count}")


def make_payroll(company, employees):
	payable_account = company.default_payroll_payable_account or frappe.db.get_value(
		"Account", {"account_name": "Payroll Payable", "company": company.name, "is_group": 0}
	)
	if not payable_account:
		print("  payroll skipped: no Payroll Payable account found for the company")
		return
	# Payroll needs this account typed as Payable; the standard chart leaves it blank
	if not frappe.db.get_value("Account", payable_account, "account_type"):
		frappe.db.set_value("Account", payable_account, "account_type", "Payable")
	if not company.default_payroll_payable_account:
		company.db_set("default_payroll_payable_account", payable_account)
	salary_account = frappe.db.get_value(
		"Account", {"account_name": "Salary", "company": company.name, "is_group": 0}
	)

	# The deduction is a share of Basic, which is already prorated, so it must not be prorated again
	components = [
		("Basic Salary", "BS", "Earning", "base * 0.6", salary_account, 1),
		("House Rent Allowance", "HRA", "Earning", "base * 0.3", salary_account, 1),
		("Transport Allowance", "TA", "Earning", "base * 0.1", salary_account, 1),
		("Provident Fund", "PF", "Deduction", "BS * 0.1", payable_account, 0),
	]
	for name, abbr, component_type, _formula, account, prorated in components:
		if frappe.db.exists("Salary Component", name):
			continue
		doc = frappe.new_doc("Salary Component")
		doc.update(
			{
				"salary_component": name,
				"salary_component_abbr": abbr,
				"type": component_type,
				"depends_on_payment_days": prorated,
			}
		)
		if account:
			doc.append("accounts", {"company": company.name, "account": account})
		doc.insert()

	structure = frappe.new_doc("Salary Structure")
	structure.update(
		{
			"__newname": f"Demo Monthly Salary - {company.abbr}",
			"company": company.name,
			"currency": company.default_currency,
			"payroll_frequency": "Monthly",
		}
	)
	for name, abbr, component_type, formula, _account, _prorated in components:
		structure.append(
			"earnings" if component_type == "Earning" else "deductions",
			{"salary_component": name, "abbr": abbr, "amount_based_on_formula": 1, "formula": formula},
		)
	structure.insert()
	structure.submit()

	last_month_start = get_first_day(add_months(today(), -1))
	last_month_end = get_last_day(last_month_start)
	assignment_start = get_first_day(add_months(today(), -3))
	for emp in employees:
		doc = frappe.new_doc("Salary Structure Assignment")
		doc.update(
			{
				"employee": emp.name,
				"salary_structure": structure.name,
				"company": company.name,
				"currency": company.default_currency,
				"from_date": max(assignment_start, emp.joined),
				"base": emp.base,
				"payroll_payable_account": payable_account,
			}
		)
		doc.insert()
		doc.submit()

	entry = frappe.new_doc("Payroll Entry")
	entry.update(
		{
			"company": company.name,
			"posting_date": last_month_end,
			"start_date": last_month_start,
			"end_date": last_month_end,
			"payroll_frequency": "Monthly",
			"currency": company.default_currency,
			"exchange_rate": 1,
			"cost_center": company.cost_center,
			"payroll_payable_account": payable_account,
			"payment_account": company.default_bank_account or company.default_cash_account,
		}
	)
	entry.fill_employee_details()
	entry.insert()
	# Submitting creates the salary slips as drafts; review and submit them from the Payroll Entry
	entry.submit()
	print(f"  payroll: {structure.name}, {len(employees)} assignments, payroll entry {entry.name}")


def make_recruitment(company):
	openings = [
		("Senior Software Engineer", "Research & Development", "Engineer"),
		("Sales Executive", "Sales", "Associate"),
	]
	applicants = [
		("Chloe Adams", 0, "Open", "Website Listing"),
		("Ravi Shankar", 0, "Replied", "Employee Referral"),
		("Mia Johansson", 0, "Rejected", "Walk In"),
		("Omar Haddad", 1, "Open", "Website Listing"),
		("Lena Novak", 1, "Accepted", "Campaign"),
	]

	opening_names = []
	for title, department, designation in openings:
		doc = frappe.new_doc("Job Opening")
		doc.update(
			{
				"job_title": title,
				"company": company.name,
				"department": get_or_make_department(department, company),
				"designation": get_or_make_designation(designation),
				"status": "Open",
				"description": f"We are hiring a {title} to join our {department} team.",
			}
		)
		doc.insert()
		opening_names.append(doc.name)

	for applicant, opening, status, source in applicants:
		frappe.get_doc(
			{
				"doctype": "Job Applicant",
				"applicant_name": applicant,
				"email_id": applicant.lower().replace(" ", ".") + "@example.com",
				"job_title": opening_names[opening],
				"status": status,
				"source": source if frappe.db.exists("Job Applicant Source", source) else None,
			}
		).insert()

	print(f"  recruitment: {len(openings)} job openings, {len(applicants)} applicants")
