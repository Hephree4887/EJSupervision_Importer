------------------------------------------------------------------------------------------------------------------------------------			
			SELECT DISTINCT		 
				 XCB.ChargeID		 
			INTO ElPaso_TX.dbo.ChargesToConvert
			FROM
				Justice.DBO.SUPCASEHDR SCH 
					INNER JOIN Justice.DBO.XCASEBASECHRG XCB ON SCH.CASEID=XCB.CASEID		--Supervision Case ID, match on Case ID
					LEFT  JOIN Justice.DBO.XCASEBASECHRG XCB2 ON XCB.CHARGEID=XCB2.CHARGEID --The related Clerk CaseID is here
		UNION 
			SELECT DISTINCT		 
				 XCB2.ChargeID		 
			FROM
				Justice.DBO.SUPCASEHDR SCH 
					INNER JOIN Justice.DBO.XCASEBASECHRG XCB ON SCH.CASEID=XCB.CASEID		--Supervision Case ID, match on Case ID
					LEFT  JOIN Justice.DBO.XCASEBASECHRG XCB2 ON XCB.CHARGEID=XCB2.CHARGEID --The related Clerk CaseID is here
	ORDER BY ChargeID;
------------------------------------------------------------------------------------------------------------------------------------
	ALTER TABLE ElPaso_TX.DBO.ChargesToConvert ALTER COLUMN ChargeID INT NOT NULL;
	ALTER TABLE ElPaso_TX.DBO.ChargesToConvert ADD CONSTRAINT PK_ChargeID PRIMARY KEY (ChargeID);
------------------------------------------------------------------------------------------------------------------------------------