CREATE DEFINER=`ibs_calc_appl`@`%` PROCEDURE `CALC_BE_NET`()
BEGIN
	/*更新推荐网的层数*/
	UPDATE AR_USER_RELATION_NEW R
	 INNER JOIN (WITH RECURSIVE T_REC AS
		            (SELECT M.USER_ID,
			                  M.PARENT_UID,
											  0 AS NODE_LEVEL
		               FROM AR_USER_RELATION_NEW M
								  WHERE M.PARENT_UID = '0'
                  UNION ALL
		             SELECT T1.USER_ID,
		                    T1.PARENT_UID,
										 	  T2.NODE_LEVEL + 1 -- 结点层级
		               FROM AR_USER_RELATION_NEW T1
		              INNER JOIN T_REC T2 ON T1.PARENT_UID = T2.USER_ID -- 从上向下
                )SELECT * FROM T_REC) A ON A.USER_ID = R.USER_ID
		 SET TOP_DEEP = NODE_LEVEL;
		COMMIT;
	/*更新安置网的层数*/
	UPDATE AR_USER_NETWORK_NEW R
	 INNER JOIN (WITH RECURSIVE T_REC AS
		            (SELECT M.USER_ID,
			                  M.PARENT_UID,
											  0 AS NODE_LEVEL
		               FROM AR_USER_NETWORK_NEW M
								  WHERE M.PARENT_UID = '0'
                  UNION ALL
		             SELECT T1.USER_ID,
		                    T1.PARENT_UID,
										 	  T2.NODE_LEVEL + 1 -- 结点层级
		               FROM AR_USER_NETWORK_NEW T1
		              INNER JOIN T_REC T2 ON T1.PARENT_UID = T2.USER_ID -- 从上向下
                )SELECT * FROM T_REC) A ON A.USER_ID = R.USER_ID
		 SET TOP_DEEP = NODE_LEVEL;
		COMMIT;
END